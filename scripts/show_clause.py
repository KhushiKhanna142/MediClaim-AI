"""Look up policy clauses so you can write correct gold_clause_ids.

  python scripts/show_clause.py find <policy_id> <keyword> [<keyword2> ...]   # clause ids whose text has ALL keywords
  python scripts/show_clause.py show <policy_id> <clause_id>                   # full text of one clause
  python scripts/show_clause.py list                                           # policy ids available
"""
import json
import sys
from pathlib import Path

CHUNKS = Path("data/processed/chunks")


def parents(policy_id: str) -> list[dict]:
    f = CHUNKS / f"{policy_id}.jsonl"
    if not f.exists():
        sys.exit(f"no such policy_id: {policy_id} (try: python scripts/show_clause.py list)")
    return [r for r in map(json.loads, f.read_text().splitlines()) if r["type"] == "parent"]


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == "list":
        print("\n".join(sorted(p.stem for p in CHUNKS.glob("*.jsonl"))))
    elif cmd == "find" and len(argv) >= 3:
        kws = [k.lower() for k in argv[2:]]
        for p in parents(argv[1]):
            if all(k in p["text"].lower() for k in kws):
                print(f"{p['clause_id']:28} p{p['page_start']:<3} {p['section'][:34]:34} | {p['text'][:90]!r}")
    elif cmd == "show" and len(argv) == 3:
        hits = [p for p in parents(argv[1]) if p["clause_id"] == argv[2] or p["chunk_id"].endswith("::" + argv[2])]
        if not hits:
            sys.exit("clause not found; use 'find' to see ids")
        for p in hits:
            print(f"--- {p['chunk_id']}  (pages {p['page_start']}-{p['page_end']}, section: {p['section']})\n{p['text']}\n")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])