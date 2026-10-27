"""Offline, manifest-approved reference retrieval. No model, network, or agent writes.

The index is a disposable snapshot; the manifest and source files are authoritative.
Token counts are conservative UTF-8 byte/3 estimates, not a model tokenizer.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


class KnowledgeError(ValueError):
    pass


def token_estimate(value):
    return math.ceil(len(str(value).encode("utf-8")) / 3)


@dataclass(frozen=True)
class Limits:
    chunk_tokens: int = 350
    max_results: int = 3
    context_tokens: int = 1000
    max_document_bytes: int = 1_000_000
    max_corpus_bytes: int = 16_000_000

    def __post_init__(self):
        for name, low, high in (("chunk_tokens", 64, 400), ("max_results", 1, 3),
                                ("context_tokens", 128, 1000), ("max_document_bytes", 1, 1_000_000),
                                ("max_corpus_bytes", 1, 16_000_000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise KnowledgeError(f"{name} must be an integer in {low}..{high}")

    @classmethod
    def environment(cls):
        try:
            return cls(chunk_tokens=int(os.environ.get("INVERSE_REFERENCE_CHUNK_TOKENS", "350")),
                       max_results=int(os.environ.get("INVERSE_REFERENCE_MAX_RESULTS", "3")),
                       context_tokens=int(os.environ.get("INVERSE_REFERENCE_CONTEXT_TOKENS", "1000")))
        except ValueError as e:
            raise KnowledgeError(str(e)) from e


def enabled():
    return os.environ.get("INVERSE_ENGINEERING_ENABLED", "1").strip().lower() not in ("0", "off", "false", "no")


def index_path(root="."):
    path = Path(os.environ.get("INVERSE_ENGINEERING_DB") or "state/engineering/knowledge.sqlite3")
    return path if path.is_absolute() else Path(root) / path


def _inside(root, relative):
    if not isinstance(relative, str) or "\\" in relative:
        raise KnowledgeError("source path must be a relative POSIX path")
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or any(p.startswith(".") or ":" in p for p in rel.parts):
        raise KnowledgeError("source path traversal or hidden path refused")
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise KnowledgeError("source must be a file inside the approved source directory")
    return path


def _read(path, limit):
    with path.open("rb") as f:
        raw = f.read(limit + 1)
    if len(raw) > limit:
        raise KnowledgeError(f"oversized input: {path.name}")
    return raw


def chunks(text, target=350):
    """Markdown headings and plain-text paragraphs; never cross section boundaries."""
    section, lines = "Introduction", []
    sections = []
    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            if lines:
                sections.append((section, "\n".join(lines)))
            section, lines = heading[1][:160], []
        else:
            lines.append(line)
    sections.append((section, "\n".join(lines)))
    for section, body in sections:
        # Character windows also bound pathological single-word documents.
        body = re.sub(r"\s+", " ", body).strip()
        part, number = "", 1
        word_chars = min(120, max(1, target // 2))  # even four-byte Unicode words fit the token estimate
        for word in re.findall(rf"\S{{1,{word_chars}}}", body):
            candidate = (part + " " + word).strip()
            if part and token_estimate(candidate) > target:
                yield section, number, part
                number, part = number + 1, word
            else:
                part = candidate
        if part:
            yield section, number, part


def rebuild(manifest, source_root, database, limits=None):
    """Explicit administrator operation. Validate everything before atomic replacement."""
    limits = limits or Limits.environment()
    root, database = Path(source_root).resolve(), Path(database).resolve()
    if database == Path(manifest).resolve():
        raise KnowledgeError("index must not overwrite its source manifest")
    try:
        spec = json.loads(_read(Path(manifest), 256_000).decode("utf-8"))
        sources = spec["sources"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as e:
        raise KnowledgeError(f"invalid source manifest: {e}") from e
    if spec.get("schema_version") != 1 or not isinstance(sources, list) or not 1 <= len(sources) <= 100:
        raise KnowledgeError("manifest requires schema_version 1 and 1..100 sources")
    documents, seen_ids, seen_content, total, duplicates = [], set(), set(), 0, 0
    for source in sources:
        if not isinstance(source, dict) or source.get("approved") is not True:
            raise KnowledgeError("every source must be explicitly approved")
        for key in ("document_id", "title", "source_url", "license", "version", "domain", "sha256"):
            if not isinstance(source.get(key), str) or not source[key].strip() or len(source[key]) > 240:
                raise KnowledgeError(f"invalid source metadata: {key}")
        if source["document_id"] in seen_ids:
            raise KnowledgeError("duplicate document_id")
        seen_ids.add(source["document_id"])
        url = urlsplit(source["source_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise KnowledgeError("source_url must be an attribution-only HTTPS URL")
        path = _inside(root, source.get("path"))
        if path == database or path.suffix.lower() not in (".md", ".txt"):
            raise KnowledgeError("only approved Markdown and UTF-8 text files are supported")
        raw = _read(path, limits.max_document_bytes)
        total += len(raw)
        if total > limits.max_corpus_bytes:
            raise KnowledgeError("corpus byte limit exceeded")
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source["sha256"]:
            raise KnowledgeError(f"content hash mismatch: {source['document_id']}")
        if digest in seen_content:
            duplicates += 1
            continue
        seen_content.add(digest)
        try:
            text = raw.decode("utf-8")
        except UnicodeError as e:
            raise KnowledgeError("sources must be UTF-8") from e
        parts = list(chunks(text, limits.chunk_tokens))
        if not parts or sum(len(d[1]) for d in documents) + len(parts) > 5000:
            raise KnowledgeError("empty document or corpus chunk limit exceeded")
        documents.append((source, parts))
    if any(_inside(root, s[0]["path"]) == database for s in documents):
        raise KnowledgeError("index must not overwrite a source")
    database.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="knowledge-", suffix=".sqlite3", dir=database.parent)
    os.close(fd)
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with closing(sqlite3.connect(temp)) as db, db:
            db.executescript("""
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE documents(document_id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
                CREATE TABLE chunks(id TEXT PRIMARY KEY, document_id TEXT NOT NULL, section TEXT NOT NULL,
                                    excerpt TEXT NOT NULL, content_hash TEXT NOT NULL);
                CREATE VIRTUAL TABLE search USING fts5(chunk_id UNINDEXED, title, section, excerpt,
                                                      tokenize='unicode61');
            """)
            db.execute("INSERT INTO metadata VALUES ('schema_version','1')")
            for source, parts in documents:
                metadata = {k: v for k, v in source.items() if k not in ("path", "approved")}
                metadata["indexed_at"] = timestamp
                db.execute("INSERT INTO documents VALUES (?,?)", (source["document_id"], json.dumps(metadata)))
                for section, number, excerpt in parts:
                    digest = hashlib.sha256(excerpt.encode()).hexdigest()
                    identity = hashlib.sha256(f"{source['document_id']}|{section}|{number}|{digest}".encode()).hexdigest()[:24]
                    db.execute("INSERT INTO chunks VALUES (?,?,?,?,?)", (identity, source["document_id"], section, excerpt, digest))
                    db.execute("INSERT INTO search VALUES (?,?,?,?)", (identity, source["title"], section, excerpt))
        os.replace(temp, database)
        _cached_search.cache_clear()
    except sqlite3.Error as e:
        raise KnowledgeError(f"SQLite FTS5 index build failed: {e}") from e
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {"documents": len(documents), "chunks": sum(len(p) for _, p in documents),
            "duplicates": duplicates, "source_bytes": total}


STOP = set("a an the of for to and or in on is are with what how do does using use please find explain reference references engineering documentation equation equations calculate compute give show me from this that result".split())


def _terms(query):
    return list(dict.fromkeys(w.lower() for w in re.findall(r"[^\W_]{2,}", query, re.UNICODE)
                              if w.lower() not in STOP))[:12]


@lru_cache(maxsize=128)
def _cached_search(path, fingerprint, query, domain, count, limits):
    del fingerprint  # part of cache identity: an atomic rebuild invalidates previous results
    terms = _terms(query)
    if not terms:
        return "[]"
    started = time.monotonic()
    uri = Path(path).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=0.2)) as db:
        db.execute("PRAGMA query_only=ON")
        db.set_progress_handler(lambda: int(time.monotonic() - started > 0.2), 1000)
        if db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone() != ("1",):
            raise KnowledgeError("unsupported reference index version")
        # FTS syntax is generated exclusively from word tokens, never model SQL.
        match = " OR ".join('"' + word + '"' for word in terms)
        rows = db.execute("""SELECT c.id,c.section,c.excerpt,c.content_hash,d.metadata
            FROM search JOIN chunks c ON c.id=search.chunk_id
            JOIN documents d ON d.document_id=c.document_id
            WHERE search MATCH ? ORDER BY bm25(search,0,2,4,1),c.id LIMIT 50""", (match,)).fetchall()
    results = []
    for identity, section, excerpt, digest, metadata in rows:
        source = json.loads(metadata)
        if domain and source["domain"] != domain:
            continue
        # Use the complete candidate vocabulary; only queries are capped.
        words = set(re.findall(r"[^\W_]{2,}", (section + " " + excerpt + " " + source["title"]).lower()))
        if len(words.intersection(terms)) < min(2, len(terms)):
            continue
        from .injection_guard import scrub
        _, blocked = scrub([{"text": excerpt}])
        if blocked:
            continue  # keep provenance in the index; do not feed known instruction attacks to agents
        item = {**source, "source_id": source["document_id"], "chunk_id": identity,
                "section": section, "excerpt": excerpt, "content_hash": digest,
                "document_hash": source["sha256"], "trusted": False, "verified": False,
                "excerpt_truncated": False}
        # Include metadata overhead in the payload budget, trimming only excerpts.
        while item["excerpt"] and token_estimate(json.dumps(results + [item], ensure_ascii=False)) > limits.context_tokens:
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", item["excerpt"])
            item["excerpt"] = " ".join(sentences[:-1]) if len(sentences) > 1 else ""
            item["excerpt_truncated"] = True
        if not item["excerpt"]:
            break
        results.append(item)
        if len(results) >= count:
            break
    return json.dumps(results, ensure_ascii=False)


def search(database, query, domain=None, max_results=3, limits=None):
    """Read-only agent API; errors are data and a missing DB is never created."""
    t0 = time.perf_counter()
    try:
        if not enabled():
            return {"status": "disabled", "results": [], "error": "engineering references are disabled"}
        limits = limits or Limits.environment()
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
            raise KnowledgeError("query must contain 1..500 characters")
        if domain is not None and (not isinstance(domain, str) or not re.fullmatch(r"[a-z][a-z_-]{0,31}", domain)):
            raise KnowledgeError("invalid engineering domain")
        if type(max_results) is not int or max_results < 1:
            raise KnowledgeError("max_results must be a positive integer")
        path = Path(database).resolve()
        if not path.is_file():
            raise KnowledgeError("reference index is missing; run the explicit rebuild command")
        stat = path.stat()
        results = json.loads(_cached_search(str(path), (stat.st_mtime_ns, stat.st_size, stat.st_ino),
                                           query.strip().lower(), domain, min(max_results, limits.max_results), limits))
        return {"status": "ok", "results": results, "estimated_tokens": token_estimate(json.dumps(results, ensure_ascii=False)),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 3), "verified": False}
    except (KnowledgeError, sqlite3.Error, OSError, ValueError, KeyError, TypeError) as e:
        return {"status": "error", "results": [], "error": str(e)[:200]}
