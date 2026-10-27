# Engineering knowledge library

The crew can search a local SQLite FTS5 snapshot of explicitly approved Markdown
and UTF-8 text files. This extends the existing toolbox and evidence contract;
it does not replace H-MEM, introduce an embedding model or start another service.
Indexing is a manual administrator operation, separate from inference.

## Build, search and disable

From the repository root, using the project's Python environment:

```powershell
.\.venv\Scripts\python.exe scripts/admin/engineering_knowledge.py rebuild
.\.venv\Scripts\python.exe scripts/admin/engineering_knowledge.py search "cantilever beam bending stress" --domain mechanical
.\.venv\Scripts\python.exe scripts/measure/knowledge_smoke.py
```

On Linux substitute `.venv/bin/python` for `.\.venv\Scripts\python.exe`.
No scientific packages are needed for retrieval; SQLite must include FTS5.
The normal application's existing requirements are needed for agent smoke tests.

The default database is `state/engineering/knowledge.sqlite3` under the checkout,
which is already ignored by Git. Override with `INVERSE_ENGINEERING_DB` (an
administrator setting, never a tool argument). The CLI accepts `--database PATH`
before its subcommand. A missing index produces a controlled error and is never
automatically created. Rebuild validates the complete manifest before replacing
the old index. A failed build leaves the last valid snapshot available.

Set `INVERSE_ENGINEERING_ENABLED=0` to disable retrieval, including automatic
reference lookup. Existing SQL and arithmetic paths continue operating. Apply
environment settings through the deployment's normal configuration mechanism;
this feature does not restart anything. Without an index, existing missions keep
their original paths except explicit reference requests, which report no index.

## Included references and attribution

`data/engineering/sources.json` approves five **original INVERSE note documents**
under this repository's Apache-2.0 license, containing 24 sections:

| File | Scope |
|---|---|
| `mechanics.md` | Force, beam stress/deflection, strain, torque, energy, oscillator identification and validation |
| `thermofluids.md` | Heat, energy balance, hydrostatics, Reynolds number, pipe loss and flow rate |
| `symbolic.md` | Symbolic solving, physical roots and calculus guidance |
| `numerical.md` | Root finding, fitting, integration and numerical precision |
| `units.md` | Dimensional analysis, conversions, temperatures and unit identity |

These are concise authored guidance and worked examples, not downloaded copies
of third-party documentation, and not independently certified engineering manuals.
The canonical source is INVERSE; each item also retains its local reference file,
section, revision and hashes so the exact source can be inspected offline.
The library-specific notes link to these background sources in the manifest:

- SymPy 1.14.0: <https://docs.sympy.org/1.14.0/tutorials/intro-tutorial/solvers.html>
- SciPy 1.18.0: <https://docs.scipy.org/doc/scipy-1.18.0/tutorial/optimize.html>
- Pint 0.25: <https://pint.readthedocs.io/en/0.25/getting/tutorial.html>

Their projects use BSD-3-Clause licenses; license references reviewed:
<https://github.com/sympy/sympy/blob/master/LICENSE>,
<https://github.com/scipy/scipy/blob/main/LICENSE.txt>, and
<https://github.com/hgrecco/pint/blob/master/LICENSE>.
`upstream_license` describes the linked background project; `license` describes
the actual indexed INVERSE document. No upstream source code or manual is bundled.
No OpenStax content is included. Fluids and thermo remain future extensions.

## Approving a local document

1. Review the document's provenance, license and suitability for the intended use.
   Obtain permission where necessary; do not infer that public access permits reuse.
2. Place the approved `.md` or `.txt` under `data/engineering/` (or an explicitly
   selected source root). Use Markdown headings to identify sections.
3. Add a manifest entry with `document_id`, relative `path`, `title`, HTTPS
   attribution `source_url`, `license`, `version`, lowercase `domain`, `approved: true`
   and the exact file-byte `sha256`. Optional background-source metadata is retained.
4. Generate the hash, for example:

   ```powershell
   .\.venv\Scripts\python.exe -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('data/engineering/example.md').read_bytes()).hexdigest())"
   ```

5. Review the manifest and source together, rebuild explicitly, and run retrieval
   tests. Editing an approved file requires a new reviewed hash and version.

There is no URL ingestion, crawler, repository clone, PDF extraction or background
updater. Attribution URLs are stored as metadata and never fetched by ingestion
or search. Paths cannot escape the approved root, including through symlinks;
hidden files, parent traversal and unsupported file types are refused.
Duplicate IDs are errors; identical file contents under different IDs are indexed
only once. Rebuild is a complete snapshot, so removed manifest entries disappear.
Chunk IDs are stable for unchanged document ID, section, part and content.
The indexing timestamp changes on rebuild but retrieval ordering is stable for
the same snapshot. Operators should rebuild while no readers are active on Windows;
an open reader can cause atomic replacement to fail without changing the old file.

## Retrieval and agent integration

`engineering_reference_search(query, domain=None, max_results=3)` is registered in
`Tools.SPECS` and executed by `Tools.call()`, which enforces per-expert grants and
charges the existing tool budget. It opens SQLite with `mode=ro` and
`PRAGMA query_only=ON`. Queries use generated word tokens and parameterized SQL,
not arbitrary FTS or SQL supplied by an agent. BM25 ranks candidates with a stable
chunk-ID tie break. A small lexical overlap threshold avoids single incidental
word matches for multiword queries; it is not semantic relevance verification.

- **Scout:** explicit reference/documentation tasks, or supported engineering
  topics without equipment-data wording, use deterministic retrieval when an index
  is available. No model call is needed for that lookup. SQL work retains its old
  guard, query loop and evidence behavior. Mixed tasks should use separate steps.
- **Ada:** receives the new tool in its existing loop. Full bounded reference
  payloads reach the model without cutting metadata in the middle of JSON.
- **Euler:** receives bounded reference evidence from dependency tasks or performs
  one charged explicit lookup for supported topics. Documentation is marked as
  untrusted supporting data, separate from accepted numerical context.
- **Vera:** sees `type: reference` evidence with source metadata and an unchecked
  notice. These items do not satisfy the existing code-only acceptance predicate.
- **Atlas:** preserves normal `[Tn.En]` evidence and adds reference-source links,
  versions and licenses. Dependency edges retain bounded reference attribution.
- **Forge:** can grant the explicit search capability, but only within its enforced
  grantable tool list and fast/deep lanes. Planner-generated experts use the same
  tool restriction. Web, write and arbitrary execution permissions are not granted.
- **Sentinel/Warden:** no new tools or background indexing behavior. Sentinel's
  existing repository reads can inspect this integration.

Reference-bearing expert results deliberately emit no persistent findings. The
reference documents do not enter H-MEM as validated experience, including through
an expert consultation. This conservative restriction can later be relaxed only
when structured engineering validation exists.

## Limits and resource considerations

| Environment setting | Default | Allowed range |
|---|---|---|
| `INVERSE_REFERENCE_CHUNK_TOKENS` | 350 | 64–400 |
| `INVERSE_REFERENCE_MAX_RESULTS` | 3 | 1–3 |
| `INVERSE_REFERENCE_CONTEXT_TOKENS` | 1000 | 128–1000 |

Counts conservatively estimate tokens as UTF-8 bytes divided by three, rounded up;
they are not measurements from the serving model's tokenizer. The total returned
result-list budget includes metadata as well as excerpts. Results may contain
fewer than three chunks. Excerpts may be shortened at sentence boundaries, flagged
with `excerpt_truncated`; `content_hash` identifies the original stored chunk and
`document_hash` identifies the approved file, not the shortened excerpt.

Ingestion caps each file at 1 MB, the corpus at 16 MB, the manifest at 256 KB,
sources at 100 and chunks at 5,000. Search caps query length at 500 characters,
unique terms at 12 and ranked candidates at 50. SQLite has a 200 ms progress-handler
deadline and 200 ms lock timeout; these are cooperative query bounds, not hard OS
resource isolation. Large-corpus search quality is not established.

A 128-entry in-process LRU caches results by query, limits and index file identity.
Callers receive independent decoded copies. Rebuild clears the cache in the indexing
process; other readers invalidate through file identity/mtime/size. No connection is
kept open. The initial index is approximately 124 KiB. Inference still dominates
CPU workload, and added context can slow model calls. No model/provider/concurrency
or global prompt-budget setting is changed.

## Security and known verification limits

Documents are data, never permission grants, system prompts or executable code.
The existing injection-pattern scrubber withholds known instruction attacks during
retrieval; it is heuristic and does not solve prompt injection. Other retrieved
text remains explicitly untrusted. Source approval, bounded context and existing
tool authorization are required boundaries. A trusted administrator controls the
manifest and database; this is not a hostile multi-user database service.

The existing verifier still discards numeric signs, does not bind units to values,
and can retain an answer after reviewer failure. Three strict expected-failure
tests record those limitations without silently rewriting the subsystem. A model
review of references is not independent physics verification. Do not use this
feature to claim verified numerical correctness. Reference-derived findings are
not persisted until a separate reliability/typed-calculation change establishes
that guarantee.

No executable Pint, SymPy or SciPy operation is shipped. A future operation needs
typed inputs, units, finite results, bounded expression grammar, process deadlines,
library/version metadata and independent checks. Avoid arbitrary `eval`, unrestricted
symbolic parsing and solver callables supplied by retrieved documents.

## Testing and measurements

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_engineering_knowledge.py
.\.venv\Scripts\python.exe -m pytest -q tests --ignore=tests/test_integration.py --ignore=tests/test_markovian.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_markovian.py -k "not reference_engine"
.\.venv\Scripts\python.exe scripts/measure/knowledge_smoke.py
```

The offline smoke creates a temporary database, builds via the public CLI, searches
in a fresh process, checks five fixed engineering domains, measures cold/warm
retrieval and Python allocations, and runs Scout→Euler→Vera→Atlas and Ada→Vera→Atlas
through actual agent code with scripted model replies. It verifies source retention,
task completion and no reference promotion to shared memory. It never contacts
production services. This is functional integration evidence, not live-model quality.

For a later live A/B evaluation, use the same frozen five task fixtures in
`knowledge_smoke.py`, expand them with the worked-example inputs and ground truth
from these notes, and score named quantities, units, assumptions and citations.
Run isolated identical memory snapshots and identical model routes with retrieval
disabled/enabled. Keep accuracy, calls, tokens and end-to-end latency separate.
Do not use the existing magnitude-only benchmark grader as engineering validation.
No inference speedup or answer-accuracy improvement is claimed by this feature.
