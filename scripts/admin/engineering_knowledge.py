"""Explicit offline administration: rebuild approved local sources or query the index."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from inverse_core.knowledge import KnowledgeError, index_path, rebuild, search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=index_path(ROOT))
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("rebuild")
    build.add_argument("--sources", type=Path, default=ROOT / "data/engineering")
    build.add_argument("--manifest", type=Path, default=ROOT / "data/engineering/sources.json")
    query = commands.add_parser("search")
    query.add_argument("query")
    query.add_argument("--domain")
    query.add_argument("--max-results", type=int, default=3)
    args = parser.parse_args()
    try:
        if args.command == "rebuild":
            out = rebuild(args.manifest, args.sources, args.database)
        else:
            out = search(args.database, args.query, args.domain, args.max_results)
        print(json.dumps(out, indent=2, ensure_ascii=True))
        return int(out.get("status") in ("error", "disabled"))
    except (KnowledgeError, OSError) as e:
        print(json.dumps({"status": "error", "error": str(e)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
