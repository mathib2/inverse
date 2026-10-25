"""Tools an expert may call, by name from experts/*.yaml. All read-only and bounded: SQL goes through the same guard as the
Research expert, arithmetic through safe_eval, and files are read only inside the repository root (code the team owns),
never secrets. A config that names an unknown tool is refused when the registry loads; a call to a tool the expert was not
given comes back as an error the model can see."""
from __future__ import annotations

import fnmatch
import os
import re
import threading

import requests

from .expert import ExpertBudget, Task
from .experts import check_sql, safe_eval

SECRET_GLOBS = (".env", ".env.*", "*.pem", "*.key", "id_*", "*.p12", "*.pfx", "secrets.toml", "*.kdbx", "*.jsonl", "*.local.yaml")   # the last two are live state, not code
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "runs", "vendor", ".state", ".pytest_cache", "experts.local", "council", "state", "queue"}
TEXT_EXT = {".py", ".md", ".txt", ".yaml", ".yml", ".toml", ".json", ".ts", ".js", ".sh", ".cfg", ".ini", ".sql", ".html", ".css", ".example"}
CODE_EXT = {".py", ".ts", ".js", ".sh", ".yaml", ".yml", ".toml", ".cfg", ".ini"}
MAX_FILE_CHARS, MAX_HITS, MAX_LIST = 8000, 40, 300
CODE_TOOLS = {"scan", "read_file", "grep", "list_files"}      # an expert holding any of these reviews code: scope-checked by the Lead, not consultable
CONSULT_BUDGET = {"tool_calls": 3, "tokens": 20000, "seconds": 120}   # what a consulted expert may spend answering one question
_consult = threading.local()                                   # nesting guard: a consulted expert does not consult another one

# Deterministic weak-spot rules (name, severity, regex, what a hit means). The model triages hits; it cannot invent one.
SCAN_RULES = [
    ("exec_from_string", "high", r"\b(eval|exec)\s*\(", "code is executed from a string"),
    ("shell_true", "high", r"shell\s*=\s*True", "a shell command is built from program values"),
    ("os_system", "high", r"\bos\.system\s*\(", "a shell command string is executed"),
    ("unsafe_deserialize", "high", r"\bpickle\.loads?\s*\(|\byaml\.(load|unsafe_load)\s*\((?![^)]*SafeLoader)|\bmarshal\.loads?\s*\(",
     "untrusted data could become code when it is deserialized"),
    ("hardcoded_secret", "high", r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*['\"][A-Za-z0-9_\-/+.]{12,}['\"]", "a credential may be written in the code"),
    ("tls_off", "medium", r"verify\s*=\s*False", "TLS certificate checks are turned off"),
    ("sql_from_strings", "medium", r"(?i)(f['\"][^'\"]*\b(select|insert|update|delete)\b[^'\"]*\{|['\"]\s*(select|insert|update|delete)\b[^'\"]*['\"]\s*(\+|%|\.format\())",
     "SQL is built from strings; identifiers or values may be injected"),
    ("bind_all", "medium", r"\b0\.0\.0\.0\b", "a service listens on every network interface"),
    ("mktemp", "medium", r"\btempfile\.mktemp\s*\(", "a predictable temp file name can be raced"),
    ("world_writable", "medium", r"\b0o?777\b|chmod\s+777", "a path is made writable by everyone"),
    ("no_timeout", "low", r"\brequests\.(get|post|put|delete|head)\s*\((?![^)]*timeout)[^)]*\)", "a network call has no timeout"),
    ("silenced_errors", "low", r"except\s*(\w+\s*)?:\s*\n\s*pass\b", "errors are silenced"),
    ("debug_on", "low", r"\bdebug\s*=\s*True", "debug mode is on"),
    ("plain_http", "low", r"['\"]http://(?!127\.0\.0\.1|localhost)", "an unencrypted URL is used"),
]
_SEV = {"high": 0, "medium": 1, "low": 2}


class ToolError(ValueError):
    pass


class Tools:
    """Bound to one run through Ctx (Zetaris client, injection guard, repo root); TeamMemory is set per task by the expert."""

    SPECS = {
        "run_sql": ("One read-only SELECT on the Zetaris tables obs.equipment_table, obs.sensors_table, obs.maintenance_table, obs.*_samples. args: {sql}", ("sql",)),
        "calc": ("Arithmetic: numbers, + - * / ** %, sqrt log exp sin cos abs log10, pi, e. args: {expr}", ("expr",)),
        "list_files": ("Files in this repository (code we own). args: {path?, pattern?}, e.g. {\"path\":\"core\",\"pattern\":\"*.py\"}", ()),
        "read_file": ("A repository file with line numbers. args: {path, start?, end?}", ("path",)),
        "grep": ("Regex search across repository files. args: {pattern, path?, glob?}", ("pattern",)),
        "scan": ("Deterministic weak-spot scan of repository code: fixed rules, each with a severity. args: {path?}", ()),
        "memory": ("What the team already found or ruled out in earlier tasks and runs. args: {}", ()),
        "ask_expert": ("Ask another expert of the team one question and get its answer with evidence (it spends part of the run budget). args: {expert, question}", ("expert", "question")),
        "post_message": ("Leave a short note for another expert (or \"all\") that they see with their next task. args: {to, text}", ("to", "text")),
        "read_messages": ("Notes, questions and results other experts addressed to you or to all in this run. args: {}", ()),
        "propose": ("File a proposal for the council (decided later, costs nothing now). args: {k: cfg|mission|note|agent|code, t: <agent, mission, shared or repo>, w: <the change>, y: <why>, p: {<the exact change>}, e: [evidence refs]}", ("k", "t", "w")),
        "support": ("Back an open council proposal by its id. args: {id}", ("id",)),
    }

    def __init__(self, ctx, allowed=None, owner=""):
        self.ctx, self.root = ctx, os.path.realpath(getattr(ctx, "root", ".") or ".")
        self.allowed = [t for t in (allowed or list(self.SPECS)) if t in self.SPECS]
        self.memory, self.owner, self.task_id = None, owner, None            # set per task by the expert that holds this toolbox

    def describe(self):
        return "\n".join(f"- {n}: {self.SPECS[n][0]}" for n in self.allowed)

    def call(self, name, args, budget, who=""):
        """Runs one tool. Unknown or disallowed tools and bad arguments come back as {"error": ...} so the model can recover;
        every call, failed or not, is charged to the expert's budget and traced."""
        args = args if isinstance(args, dict) else {}
        budget.charge_tool()
        if name not in self.allowed:
            out = {"error": f"tool {name!r} is not available to this expert (allowed: {', '.join(self.allowed) or 'none'})"}
        else:
            missing = [a for a in self.SPECS[name][1] if a not in args]
            if missing:
                out = {"error": f"{name} needs {missing}"}
            else:
                try:
                    out = getattr(self, "_" + name)(**args)
                except (ToolError, ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError, OSError, re.error,
                        requests.RequestException) as e:
                    out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        self.ctx.trace.event("tool", agent=who, tool=name, args=str(args)[:200], error=out.get("error") if isinstance(out, dict) else None)
        return out

    # --- files: inside the repository only, never secrets -----------------------------------------------------------------
    def _inside(self, rel):
        """A path inside the repository root that is not a secret and not under a skipped folder (.git, runs, vendor, ...)."""
        p = os.path.realpath(os.path.join(self.root, str(rel)))
        if p != self.root and not p.startswith(self.root + os.sep):
            raise ToolError(f"{rel!r} is outside the repository; experts read only code we own")
        if any(fnmatch.fnmatch(os.path.basename(p), g) for g in SECRET_GLOBS):
            raise ToolError(f"{rel!r} may hold secrets and is never read")
        parts = os.path.relpath(p, self.root).split(os.sep) if p != self.root else []
        if any(part in SKIP_DIRS or part.startswith(".") for part in parts):
            raise ToolError(f"{rel!r} is under a folder experts do not read (" + ", ".join(sorted(SKIP_DIRS)) + " and dot-folders)")
        return p

    def _rel(self, p):
        return os.path.relpath(p, self.root).replace(os.sep, "/")

    def _walk(self, path="."):
        top = self._inside(path)
        if os.path.isfile(top):
            yield top
            return
        for d, dirs, files in os.walk(top):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
            for f in sorted(files):
                if os.path.splitext(f)[1] in TEXT_EXT and not any(fnmatch.fnmatch(f, g) for g in SECRET_GLOBS):
                    yield os.path.join(d, f)

    def _list_files(self, path=".", pattern="*"):
        out = [self._rel(p) for p in self._walk(path) if fnmatch.fnmatch(os.path.basename(p), pattern)]
        return {"files": out[:MAX_LIST], "truncated": max(0, len(out) - MAX_LIST)}

    def _read_file(self, path, start=1, end=None):
        p = self._inside(path)
        if not os.path.isfile(p):
            raise ToolError(f"{path!r} is not a file")
        if os.path.splitext(p)[1] not in TEXT_EXT:
            raise ToolError(f"{path!r} is not a text file experts read")
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        start, end = max(1, int(start)), min(len(lines), int(end or len(lines)))
        text = "\n".join(f"{i:5d}| {lines[i - 1]}" for i in range(start, end + 1))
        return {"path": self._rel(p), "lines": len(lines), "start": start, "end": end, "text": text[:MAX_FILE_CHARS], "truncated": len(text) > MAX_FILE_CHARS}

    def _grep(self, pattern, path=".", glob="*"):
        rx, hits = re.compile(pattern), []
        for p in self._walk(path):
            if not fnmatch.fnmatch(os.path.basename(p), glob):
                continue
            with open(p, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if rx.search(line):
                        hits.append({"file": self._rel(p), "line": i, "text": line.rstrip()[:200]})
                        if len(hits) >= MAX_HITS:
                            return {"hits": hits, "truncated": True}
        return {"hits": hits, "truncated": False}

    def _scan(self, path="."):
        """Fixed rules over code and config files. tests/ is skipped: tests hold deliberate bad inputs."""
        hits, scanned = [], 0
        for p in self._walk(path):
            rel = self._rel(p)
            if os.path.splitext(p)[1] not in CODE_EXT or rel.startswith("tests/"):
                continue
            scanned += 1
            with open(p, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            for i, line in enumerate(lines):
                pair = line + "\n" + (lines[i + 1] if i + 1 < len(lines) else "")      # two lines, so a rule may look one line ahead
                for rule, sev, rx, meaning in SCAN_RULES:
                    m = re.search(rx, pair)
                    if m and m.start() <= len(line):
                        hits.append({"file": rel, "line": i + 1, "text": line.strip()[:160], "rule": rule, "severity": sev, "meaning": meaning})
        hits.sort(key=lambda h: (_SEV[h["severity"]], h["file"], h["line"]))
        return {"hits": hits[:MAX_HITS], "total": len(hits), "files_scanned": scanned, "truncated": len(hits) > MAX_HITS}

    # --- data, arithmetic, memory --------------------------------------------------------------------------------------------
    def _run_sql(self, sql):
        if self.ctx.zetaris is None:
            raise ToolError("Zetaris is not connected")
        sql = check_sql(str(sql))
        cache = getattr(self.ctx, "sql_cache", None)
        if cache is not None and sql in cache:
            rows = cache[sql]
            self.ctx.trace.event("sql_cache_hit", sql=sql[:120])
        else:
            rows = self.ctx.zetaris.sql(sql, limit=50)
            if cache is not None:
                cache[sql] = rows
        from ..agents.guard import scrub
        rows, blocked = scrub(rows)                                             # untrusted text never reaches a model raw, whatever the column is called
        if blocked:
            self.ctx.trace.event("injection_guard", agent=self.owner, blocked=blocked[:5])
        return {"sql": sql, "rows": rows[:50], "count": len(rows)}

    def _calc(self, expr):
        return {"expr": str(expr), "value": safe_eval(str(expr))}

    # --- talking to other experts ---------------------------------------------------------------------------------------------
    def _team(self):
        reg = getattr(self.ctx, "registry", None)
        if reg is None:
            raise ToolError("no expert registry is attached to this run")
        return reg

    def _bus(self):
        bus = getattr(self.ctx, "bus", None)
        if bus is None:
            from .bus import Bus
            bus = self.ctx.bus = Bus()
        return bus

    def _ask_expert(self, expert, question):
        """Runs another expert on one question with a small budget and returns its answer with evidence. The exchange goes on the
        message bus and into the trace. Not allowed: itself, an expert that reviews code or builds experts (those take tasks only from
        the lead, after its scope check), and a second level of consultation."""
        reg, name, me = self._team(), str(expert), self.owner or "an expert"
        if name not in reg.experts:
            raise ToolError(f"no expert named {name!r} on the team (known: {', '.join(reg.names())})")
        if name == self.owner:
            raise ToolError("an expert cannot consult itself")
        target = reg.experts[name]
        if set(getattr(target, "tools", None) or []) & CODE_TOOLS or reg.configs[name].get("kind") == "architect":
            raise ToolError(f"{name} reviews code or builds experts and takes tasks only from the lead")
        if getattr(_consult, "depth", 0) >= 1:
            raise ToolError("a consulted expert cannot consult another one (one level deep)")
        bus = self._bus()
        bus.post(me, name, question, type="question", task=self.task_id)
        _consult.depth = getattr(_consult, "depth", 0) + 1
        try:
            res = target.run(Task(f"{self.task_id or me}>{name}", str(question), name), self.memory, ExpertBudget(**CONSULT_BUDGET))
        except Exception as e:                                                # the consulted expert's failure is the caller's tool error, never the run's
            why = f"{type(e).__name__}: {str(e)[:160]}"
            bus.post(name, me, "could not answer: " + why, type="answer", task=self.task_id)
            self.ctx.trace.event("consult", **{"from": me, "to": name, "question": str(question)[:200], "ok": False, "error": why})
            raise ToolError(f"{name} could not answer: {why}")
        finally:
            _consult.depth -= 1
        bus.post(name, me, res.answer, type="answer", task=self.task_id, confidence=res.confidence)
        self.ctx.trace.event("consult", **{"from": me, "to": name, "question": str(question)[:200], "ok": True, "confidence": res.confidence,
                                            "evidence": len(res.evidence)})
        return {"expert": name, "answer": res.answer, "confidence": res.confidence, "evidence": [str(e.get("detail") or "")[:200] for e in res.evidence[:4]],
                "not_checked": [str(n) for n in res.not_checked[:4]]}

    def _post_message(self, to, text):
        """A note another expert sees with its next task in this run (everyone, with "all")."""
        to = str(to)
        if to != "all" and to not in self._team().experts:
            raise ToolError(f"no expert named {to!r} on the team (use a name or \"all\")")
        m = self._bus().post(self.owner or "an expert", to, str(text), type="note", task=self.task_id)
        return {"delivered_to": to, "message": m["n"]}

    def _propose(self, **args):
        council = getattr(self.ctx, "council", None)
        if council is None:
            raise ToolError("no council is attached to this run")
        p = council.file(args, by=self.owner or "an expert", run=getattr(self.ctx.trace, "dir", ""))
        if p is None:
            raise ToolError("the proposal was not accepted by the wire protocol (see the trace: proposal_dropped)")
        return {"id": p["id"], "status": p["status"], "backers": len(p["backers"])}

    def _support(self, id):
        council = getattr(self.ctx, "council", None)
        if council is None:
            raise ToolError("no council is attached to this run")
        p = council.support(str(id), self.owner or "an expert")
        if p is None:
            raise ToolError(f"no open proposal {id!r}")
        return {"id": p["id"], "backers": len(p["backers"])}

    def _read_messages(self):
        return {"messages": [{k: m.get(k) for k in ("from", "to", "type", "task", "text")} for m in self._bus().inbox(self.owner or "", limit=12)]}


    def _memory(self):
        if self.memory is None:
            return {"findings": [], "refuted": []}
        return {"findings": [str(f.get("form", ""))[:200] for f in self.memory.findings()][-10:], "refuted": sorted(self.memory.refuted())[-10:]}
