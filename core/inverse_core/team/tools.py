"""Tools an expert may call, by name from experts/*.yaml. All read-only and bounded: SQL goes through the same guard as the
Research expert, arithmetic through safe_eval, and files are read only inside the repository root (code the team owns),
never secrets. A config that names an unknown tool is refused when the registry loads; a call to a tool the expert was not
given comes back as an error the model can see."""
from __future__ import annotations

import fnmatch
import inspect
import os
import re
import threading
from urllib.parse import urlparse

import requests

from .expert import ExpertBudget, Task
from .reasoning import safe_eval
from .sql_guard import check_sql

SECRET_GLOBS = (".env", ".env.*", "*.pem", "*.key", "id_*", "*.p12", "*.pfx", "secrets.toml", "*.kdbx", "*.jsonl", "*.local.yaml")   # the last two are live state, not code
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "runs", "vendor", ".state", ".pytest_cache", "experts.local", "council", "state", "queue"}
TEXT_EXT = {".py", ".md", ".txt", ".yaml", ".yml", ".toml", ".json", ".ts", ".js", ".sh", ".cfg", ".ini", ".sql", ".html", ".css", ".example"}
CODE_EXT = {".py", ".ts", ".js", ".sh", ".yaml", ".yml", ".toml", ".cfg", ".ini"}
MAX_FILE_CHARS, MAX_HITS, MAX_LIST = 8000, 40, 300
CODE_TOOLS = {"scan", "read_file", "grep", "list_files"}      # an expert holding any of these reviews code: scope-checked by the Lead, not consultable
CONSULT_BUDGET = {"tool_calls": 3, "tokens": 20000, "seconds": 120}   # what a consulted expert may spend answering one question
_consult = threading.local()                                   # nesting guard: a consulted expert does not consult another one

# Deterministic weak-spot rules (name, severity, regex, what a hit means[, clear]). The model triages hits; it cannot invent one.
# A rule with a fifth element matches the opening of a call; the hit is cleared when the whole call, read bracket by bracket
# across nested calls and lines, matches `clear`. A regex alone stops at the first ')' of an inner call such as str(query),
# which once reported "no timeout" for a call that ends in timeout=20.
SCAN_RULES = [
    ("exec_from_string", "high", r"\b(eval|exec)\s*\(", "code is executed from a string"),
    ("shell_true", "high", r"shell\s*=\s*True", "a shell command is built from program values"),
    ("os_system", "high", r"\bos\.system\s*\(", "a shell command string is executed"),
    ("unsafe_deserialize", "high", r"\bpickle\.loads?\s*\(|\byaml\.unsafe_load\s*\(|\bmarshal\.loads?\s*\(",
     "untrusted data could become code when it is deserialized"),
    ("unsafe_deserialize", "high", r"\byaml\.load\s*\(", "untrusted data could become code when it is deserialized", r"SafeLoader|BaseLoader"),
    ("hardcoded_secret", "high", r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*['\"][A-Za-z0-9_\-/+.]{12,}['\"]", "a credential may be written in the code"),
    ("tls_off", "medium", r"verify\s*=\s*False", "TLS certificate checks are turned off"),
    ("sql_from_strings", "medium", r"(?i)(f['\"][^'\"]*\b(select|insert|update|delete)\b[^'\"]*\{|['\"]\s*(select|insert|update|delete)\b[^'\"]*['\"]\s*(\+|%|\.format\())",
     "SQL is built from strings; identifiers or values may be injected"),
    ("bind_all", "medium", r"\b0\.0\.0\.0\b", "a service listens on every network interface"),
    ("mktemp", "medium", r"\btempfile\.mktemp\s*\(", "a predictable temp file name can be raced"),
    ("world_writable", "medium", r"\b0o?777\b|chmod\s+777", "a path is made writable by everyone"),
    ("no_timeout", "low", r"\brequests\.(get|post|put|delete|head|patch|request)\s*\(", "a network call has no timeout", r"\btimeout\s*="),
    ("silenced_errors", "low", r"except\s*(\w+\s*)?:\s*\n\s*pass\b", "errors are silenced"),
    ("debug_on", "low", r"\bdebug\s*=\s*True", "debug mode is on"),
    ("plain_http", "low", r"['\"]http://(?!127\.0\.0\.1|localhost)", "an unencrypted URL is used"),
]
_SEV = {"high": 0, "medium": 1, "low": 2}


def call_args(text, open_at):
    """The text inside the call whose '(' is at open_at, up to its matching ')': nested brackets, strings and comments are
    stepped over, lines are crossed. None when the call never closes (the hit then stands)."""
    depth, i, quote = 0, open_at, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "#":
            j = text.find("\n", i)
            i = len(text) if j < 0 else j
            continue
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i]
        i += 1
    return None


class ToolError(ValueError):
    pass


UA = "INVERSE-crew/1.0 (+research by a local agent; read-only)"


def _private(host):
    """True for an address of this machine or a private network (the web tools never read those)."""
    import ipaddress
    import socket
    try:
        addrs = {host} if host.replace(".", "").isdigit() or ":" in host else {ai[4][0] for ai in socket.getaddrinfo(host, None)}
        return any(ipaddress.ip_address(a).is_private or ipaddress.ip_address(a).is_loopback or ipaddress.ip_address(a).is_link_local for a in addrs)
    except (socket.gaierror, ValueError):
        return True


def _untag(s):
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", s or ""))


def parse_duckduckgo(page):
    """Titles, urls and snippets from DuckDuckGo's HTML results page (its redirect links carry the real url in `uddg`)."""
    from urllib.parse import parse_qs, unquote
    from urllib.parse import urlparse as _up
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page or "", re.DOTALL)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page or "", re.DOTALL)
    out = []
    for i, (href, title) in enumerate(links):
        href = html_unescape(href)
        q = parse_qs(_up(href).query)
        url = unquote(q["uddg"][0]) if "uddg" in q else href
        out.append({"title": re.sub(r"\s+", " ", _untag(title)).strip()[:160], "url": url[:300],
                    "snippet": re.sub(r"\s+", " ", _untag(snippets[i] if i < len(snippets) else "")).strip()[:300]})
    return out


def html_unescape(s):
    import html
    return html.unescape(s or "")


def page_text(page):
    """A web page as plain text: scripts and styles dropped, tags removed, whitespace collapsed, the first 4000 characters."""
    page = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page or "")
    text = re.sub(r"\s+", " ", _untag(page)).strip()
    return text[:4000]


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
        "web_search": ("Search the web and get up to 5 results with title, url and snippet. args: {query}", ("query",)),
        "fetch_url": ("Read a public web page as plain text (the first 4000 characters). args: {url}", ("url",)),
        "edit_file": ("Replace one exact piece of text in a sandbox file with new text (old must occur once). Sandbox only. args: {path, old, new}", ("path", "old", "new")),
        "write_file": ("Write the whole content of a small sandbox file (new or existing). Sandbox only. args: {path, content}", ("path", "content")),
        "run_tests": ("Run the test suite in the sandbox and get its summary. Sandbox only. args: {}", ()),
    }

    def __init__(self, ctx, allowed=None, owner=""):
        self.ctx, self.root = ctx, os.path.realpath(getattr(ctx, "root", ".") or ".")
        self.allowed = [t for t in (list(self.SPECS) if allowed is None else allowed) if t in self.SPECS]   # an empty list means no tools, not every tool
        self.memory, self.owner, self.task_id = None, owner, None            # set per task by the expert that holds this toolbox

    def describe(self):
        text = "\n".join(f"- {n}: {self.SPECS[n][0]}" for n in self.allowed)
        if "run_sql" in self.allowed:                                           # the same value-annotated schema the research expert gets
            from .sql_guard import SCHEMA
            text += "\n" + SCHEMA
        return text

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
                fn = getattr(self, "_" + name)
                params = inspect.signature(fn).parameters
                extra = [k for k in args if k not in params] if not any(p.kind == p.VAR_KEYWORD for p in params.values()) else []
                if extra:                                                     # a note the model put inside args ("why") is not an argument
                    args = {k: v for k, v in args.items() if k not in extra}
                    self.ctx.trace.event("args_dropped", agent=who, tool=name, dropped=extra[:4])
                try:
                    out = fn(**args)
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
                text = f.read()
            lines, start = text.split("\n"), 0
            for i, line in enumerate(lines):
                pair = line + "\n" + (lines[i + 1] if i + 1 < len(lines) else "")      # two lines, so a rule may look one line ahead
                for rule, sev, rx, meaning, *clear in SCAN_RULES:
                    m = re.search(rx, pair)
                    if not m or m.start() > len(line):
                        continue
                    if clear:                                                          # the whole call decides, not the first ')'
                        args = call_args(text, start + m.end() - 1)
                        if args is not None and re.search(clear[0], args):
                            continue
                    hits.append({"file": rel, "line": i + 1, "text": line.strip()[:160], "rule": rule, "severity": sev, "meaning": meaning})
                start += len(line) + 1
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
        from ..injection_guard import scrub
        rows, blocked = scrub(rows)                                             # untrusted text never reaches a model raw, whatever the column is called
        if blocked:
            self.ctx.trace.event("injection_guard", agent=self.owner, blocked=blocked[:5])
        return {"sql": sql, "rows": rows[:12], "count": len(rows)}            # a dozen rows is what a 4B model can read; the count says the rest

    def _calc(self, expr):
        return {"expr": str(expr), "value": safe_eval(str(expr))}

    # --- the web: read-only, through the injection guard -----------------------------------------------------------------------
    def _web_search(self, query):
        r = requests.post("https://html.duckduckgo.com/html/", data={"q": str(query)[:200]}, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        results = parse_duckduckgo(r.text)[:5]
        from ..injection_guard import scrub
        results, blocked = scrub(results)
        if blocked:
            self.ctx.trace.event("injection_guard", agent=self.owner, blocked=blocked[:5], source="web_search")
        return {"query": str(query)[:200], "results": results}

    def _fetch_url(self, url):
        url = str(url).strip()
        host = (urlparse(url).hostname or "").lower()
        if urlparse(url).scheme not in ("http", "https") or not host:
            raise ToolError("fetch_url takes a public http(s) URL")
        if host in ("localhost",) or host.endswith(".local") or _private(host):
            raise ToolError("fetch_url reads public pages only, never this machine or the local network")
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20, stream=True, allow_redirects=False)
        if r.is_redirect or r.is_permanent_redirect:                           # a redirect could point at this machine or the local network: never followed blindly
            raise ToolError(f"fetch_url does not follow redirects; fetch the final address instead ({str(r.headers.get('Location', ''))[:120]})")
        r.raise_for_status()
        raw = b""
        for chunk in r.iter_content(65536):
            raw += chunk
            if len(raw) > 400000:
                break
        text = page_text(raw.decode(r.encoding or "utf-8", "replace"))
        from ..injection_guard import scrub
        rows, blocked = scrub([{"text": text}])
        if blocked:
            self.ctx.trace.event("injection_guard", agent=self.owner, blocked=blocked[:5], source="fetch_url")
        return {"url": url, "text": rows[0]["text"] if rows else "", "chars": len(text)}

    # --- the sandbox: only when this toolbox's root IS the improvement sandbox --------------------------------------------------
    def _sandbox(self):
        box = os.environ.get("INVERSE_SANDBOX")
        if not box or os.path.realpath(box) != self.root:
            raise ToolError("this tool works only in the improvement sandbox (INVERSE_SANDBOX), never in the live checkout")

    def _write_file(self, path, content):
        self._sandbox()
        p = self._inside(path)
        if os.path.splitext(p)[1] not in TEXT_EXT:
            raise ToolError(f"{path!r}: only text files may be written")
        if len(str(content)) > 60000:
            raise ToolError("write_file takes at most 60000 characters; use edit_file for a large file")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(str(content))
        return {"written": path, "chars": len(str(content))}

    def _edit_file(self, path, old, new):
        self._sandbox()
        p = self._inside(path)
        with open(p, encoding="utf-8") as f:
            text = f.read()
        old, new = str(old), str(new)
        if text.count(old) == 0:                                                # the model copied the excerpt's line numbers: strip them and try again
            bare = re.sub(r"(?m)^\s*\d+: ?", "", old)
            if bare != old and text.count(bare) == 1:
                old, new = bare, re.sub(r"(?m)^\s*\d+: ?", "", new)
        n = text.count(old)
        if n != 1:
            raise ToolError(f"old text occurs {n} times in {path}; it must occur exactly once (copy it exactly, including indentation, without line numbers)")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, 1))
        return {"edited": path, "removed_chars": len(str(old)), "added_chars": len(str(new))}

    def _run_tests(self):
        self._sandbox()
        import subprocess
        import sys
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests", "-x", "-p", "no:cacheprovider"], cwd=self.root, capture_output=True, text=True, timeout=600,
                               env={**os.environ, "PYTHONPATH": "core"})
            lines = (r.stdout + r.stderr).strip().splitlines()
            return {"returncode": r.returncode, "passed": r.returncode == 0, "summary": "\n".join(lines[-12:])[:1500]}
        except subprocess.TimeoutExpired:
            return {"returncode": 124, "passed": False, "summary": "the tests did not finish in 600 s"}

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
