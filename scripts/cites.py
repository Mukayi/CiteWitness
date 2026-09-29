#!/usr/bin/env python3
"""List the citation keys used in LaTeX sources, cross-check them against a .bib file, and dump the sentence around
every \\cite so attributions can be checked against the paper text.

    python cites.py --bib main.bib --tex main.tex sec/*.tex fig/*.tex [--json cites.json]

Prints: cited keys, keys cited but missing from the bib (compile errors), bib entries never cited, and per key the
list of (file:line, context) snippets.  Read-only.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bibtools import parse_bib  # noqa: E402

CITE_RE = re.compile(r"\\(?:cite|citep|citet|citealp|citealt|citeauthor|citeyear|parencite|textcite|autocite)\*?"
                     r"(?:\[[^\]]*\]){0,2}\{([^}]+)\}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bib", required=True)
    ap.add_argument("--tex", nargs="+", required=True, help="tex files or globs")
    ap.add_argument("--json", help="write {key: [{file, line, context}]} here")
    ap.add_argument("--context", type=int, default=160, help="characters of context on each side")
    a = ap.parse_args()

    files = sorted({f for pat in a.tex for f in glob.glob(pat)})
    uses: dict[str, list[dict]] = {}
    for f in files:
        text = open(f, encoding="utf-8", errors="replace").read()
        for m in CITE_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            ctx = " ".join(text[max(0, m.start() - a.context): m.end() + a.context].split())
            for key in m.group(1).split(","):
                key = key.strip()
                if key:
                    uses.setdefault(key, []).append({"file": f, "line": line, "context": ctx})

    bib_keys = {e["key"] for e in parse_bib(open(a.bib, encoding="utf-8", errors="replace").read())}
    cited = sorted(uses)
    missing = [k for k in cited if k not in bib_keys]
    unused = sorted(bib_keys - set(cited))

    print(f"tex files: {len(files)}   cited keys: {len(cited)}   bib entries: {len(bib_keys)}")
    print("cited:", " ".join(cited))
    print("MISSING from bib (would break the build):", " ".join(missing) or "-")
    print("bib entries not cited:", " ".join(unused) or "-")
    for k in cited:
        print(f"\n[{k}] {len(uses[k])} use(s)")
        for u in uses[k][:6]:
            print(f"  {u['file']}:{u['line']}  …{u['context']}…")
        if len(uses[k]) > 6:
            print(f"  … {len(uses[k]) - 6} more")
    if a.json:
        json.dump({"cited": cited, "missing": missing, "unused": unused, "uses": uses}, open(a.json, "w"),
                  ensure_ascii=False, indent=1)
        print(f"\n-> {a.json}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
