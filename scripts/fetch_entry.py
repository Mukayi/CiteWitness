#!/usr/bin/env python3
"""Emit a BibTeX entry built ONLY from a retrieved record.  Never fills a field from memory.

    python fetch_entry.py --arxiv 1512.03385 [--key resnet]
    python fetch_entry.py --doi 10.1109/TIP.2003.819861 [--key ssim]        # Crossref's own BibTeX
    python fetch_entry.py --dblp-key conf/nips/VaswaniSPUJGKP17 [--key attention]  # DBLP's own BibTeX
    python fetch_entry.py --title "Attention Is All You Need"   # candidates only

Rules baked in:
  * arXiv records become @article{..., journal={arXiv preprint arXiv:ID}} with the full author list verbatim.
    The arXiv comment / journal_ref are echoed as a % comment so the venue can be confirmed and added by hand;
    booktitle is NEVER filled automatically ("Accepted by X" in a comment is a claim, not a proceedings record).
  * --title prints the candidates from arXiv, Crossref and DBLP with their title-match ratio and stops.  Pick an id
    and re-run with --arxiv / --doi / --dblp-key.  No candidate is chosen for you.
  * Every emitted entry is preceded by '% source: <url> fetched <date>'.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bibtools import (arxiv_by_ids, arxiv_search_title, crossref_bibtex, crossref_search, dblp_bibtex,  # noqa: E402
                      dblp_search, title_ratio)


def protect_caps(title: str) -> str:
    """Brace words with inner capitals or all-caps acronyms so BibTeX styles keep them (ResNet, ICML, 3D)."""
    out = []
    for w in title.split():
        core = re.sub(r"[^A-Za-z0-9]", "", w)
        if len(core) > 1 and re.search(r"[A-Z]", core[1:]) and not w.startswith("{"):
            out.append("{" + w + "}")
        else:
            out.append(w)
    return " ".join(out)


def arxiv_entry(rec: dict, key: str | None) -> str:
    key = key or (re.sub(r"[^a-z]", "", rec["authors"][0].split()[-1].lower()) + rec["year"] +
                  re.sub(r"[^a-z]", "", rec["title"].split()[0].lower()))
    lines = [f"% source: {rec['url']} fetched {dt.date.today().isoformat()} (arXiv API, {rec['id_versioned']})"]
    if rec.get("comment"):
        lines.append(f"% arXiv comment: {rec['comment']}")
    if rec.get("journal_ref"):
        lines.append(f"% arXiv journal_ref: {rec['journal_ref']}")
    if rec.get("doi"):
        lines.append(f"% arXiv doi: {rec['doi']}")
    lines.append("% venue: NOT set -- confirm in a proceedings index / OpenReview before adding booktitle or journal")
    lines += [f"@article{{{key},",
              f"  title   = {{{protect_caps(rec['title'])}}},",
              f"  author  = {{{' and '.join(rec['authors'])}}},",
              f"  journal = {{arXiv preprint arXiv:{rec['id']}}},",
              f"  year    = {{{rec['year']}}},",
              f"  eprint  = {{{rec['id']}}},",
              "  archivePrefix = {arXiv}",
              "}"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--arxiv", help="arXiv id, e.g. 1512.03385")
    g.add_argument("--doi")
    g.add_argument("--dblp-key", help="e.g. conf/nips/VaswaniSPUJGKP17")
    g.add_argument("--title", help="search only; prints candidates")
    ap.add_argument("--key", help="bib key for the emitted entry")
    a = ap.parse_args()
    today = dt.date.today().isoformat()

    if a.arxiv:
        aid = re.sub(r"v\d+$", "", a.arxiv.strip())
        recs = arxiv_by_ids([aid])
        if aid not in recs:
            print(f"arXiv id {aid} not found", file=sys.stderr)
            return 2
        print(arxiv_entry(recs[aid], a.key))
        return 0
    if a.doi:
        bib = crossref_bibtex(a.doi).strip()
        if a.key:
            bib = re.sub(r"^(@\w+\{)[^,]+,", rf"\g<1>{a.key},", bib, count=1)
        print(f"% source: https://doi.org/{a.doi} fetched {today} (Crossref content negotiation)\n{bib}")
        return 0
    if a.dblp_key:
        bib = dblp_bibtex(a.dblp_key).strip()
        if a.key:
            bib = re.sub(r"^(@\w+\{)[^,]+,", rf"\g<1>{a.key},", bib, count=1, flags=re.M)
        print(f"% source: https://dblp.org/rec/{a.dblp_key} fetched {today} (DBLP)\n{bib}")
        return 0
    # --title: candidates only
    print(f"# candidates for: {a.title}\n")
    for name, fn in (("arXiv", arxiv_search_title), ("Crossref", crossref_search), ("DBLP", dblp_search)):
        try:
            hits = fn(a.title)
        except Exception as e:
            print(f"## {name}: lookup failed ({e})")
            continue
        print(f"## {name} ({len(hits)} hit(s))")
        for r in sorted(hits, key=lambda r: -title_ratio(a.title, r["title"])):
            ident = r.get("id") or r.get("doi") or r.get("key")
            venue = r.get("comment") or r.get("journal_ref") or r.get("container") or r.get("venue") or ""
            print(f"- ratio {title_ratio(a.title, r['title']):.2f} | {ident} | {r['year']} | {r['title']}\n"
                  f"    authors: {'; '.join(r['authors'][:8])}{' ...' if len(r['authors']) > 8 else ''}\n"
                  f"    venue evidence: {venue[:160] or '-'} | {r['url']}")
    print("\nPick one identifier and re-run with --arxiv / --doi / --dblp-key.  Nothing was chosen automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
