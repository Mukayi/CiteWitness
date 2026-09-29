#!/usr/bin/env python3
"""Fetch a web page (or an arXiv paper's HTML) as plain text and print every match of the given patterns with
context.  Used to confirm (a) that a paper really says what a sentence attributes to it and (b) that a title appears
in a proceedings index / programme page.

    python webgrep.py --arxiv 1706.03762 "scaled dot-product attention"     # arxiv.org/html/<id>, falls back to /abs/
    python webgrep.py --url https://proceedings.mlr.press/v267/ "<a few words of the title>"
    python webgrep.py --url <url> --dump page.txt                             # save the whole text for reading

Patterns are case-insensitive regular expressions.  Prints "0 hit(s)" explicitly when a pattern is absent -- an
absent pattern is evidence, not an error.  Read-only.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bibtools import html_to_text, polite_get  # noqa: E402


def fetch_text(url: str) -> str:
    return html_to_text(polite_get(url, min_interval=1.0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--arxiv", help="arXiv id; fetches https://arxiv.org/html/<id> (fallback: abstract page)")
    g.add_argument("--url")
    ap.add_argument("patterns", nargs="*", help="regexes to look for")
    ap.add_argument("--context", type=int, default=220)
    ap.add_argument("--max-hits", type=int, default=4)
    ap.add_argument("--dump", help="write the full plain text here")
    a = ap.parse_args()

    if a.arxiv:
        aid = re.sub(r"v\d+$", "", a.arxiv.strip())
        try:
            text, src = fetch_text(f"https://arxiv.org/html/{aid}"), f"https://arxiv.org/html/{aid}"
            if len(text) < 2000:
                raise ValueError("html version too short")
        except Exception:
            text, src = fetch_text(f"https://arxiv.org/abs/{aid}"), f"https://arxiv.org/abs/{aid} (abstract only)"
    else:
        text, src = fetch_text(a.url), a.url
    print(f"source: {src}   ({len(text)} chars of text)")
    if a.dump:
        open(a.dump, "w", encoding="utf-8").write(text)
        print(f"-> {a.dump}")
    for pat in a.patterns:
        ms = list(re.finditer(pat, text, flags=re.I))
        print(f"\n[{pat}] {len(ms)} hit(s)")
        for m in ms[:a.max_hits]:
            s, e = max(0, m.start() - a.context), min(len(text), m.end() + a.context)
            print(f"  …{text[s:e]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
