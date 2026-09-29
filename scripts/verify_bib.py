#!/usr/bin/env python3
"""Verify every entry of a .bib file against retrieved records (arXiv API, Crossref, DBLP) and report
title / author / year / venue discrepancies.  Read-only: never edits the .bib.

    python verify_bib.py main.bib [--keys k1 k2 ...] [--md report.md] [--json report.json]
                         [--index https://proceedings.mlr.press/v267/ ...]

Resolution order per entry: arXiv id found in any field -> DOI -> title search on arXiv, then Crossref, then DBLP
(a title-search hit counts only if the normalised titles agree at ratio >= 0.90).  --index URLs are proceedings /
programme pages: the entry's title is looked up in the page text to confirm or refute a claimed venue.

Verdicts:  PASS  = title, authors (surname sequence) and year agree with the record and the venue claim is confirmed
           WARN  = venue unconfirmed / year off by one / truncated author list / collective author / newer venue available
           FAIL  = no record found, title disagrees, or the author list has wrong / missing / extra names
Exit code 2 if any FAIL, 1 if only WARN, 0 if all PASS.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bibtools import (arxiv_by_ids, arxiv_search_title, compare_authors, crossref_by_doi, crossref_search,  # noqa: E402
                      dblp_search, find_arxiv_id, find_doi, html_to_text, norm_title, parse_bib, polite_get,
                      split_bib_authors, strip_tex, title_ratio)

VENUES = {  # canonical token -> strings that count as evidence (lower-case substring match)
    "neurips": ["neurips", "neural information processing", "nips"],
    "icml": ["icml", "international conference on machine learning", "proceedings of machine learning research"],
    "iclr": ["iclr", "learning representations"],
    "cvpr": ["cvpr", "computer vision and pattern recognition"],
    "iccv": ["iccv", "international conference on computer vision"],
    "eccv": ["eccv", "european conference on computer vision"],
    "emnlp": ["emnlp", "empirical methods in natural language"],
    "acl": ["annual meeting of the association for computational linguistics", " acl "],
    "aaai": ["aaai"],
    "mlsys": ["mlsys", "machine learning and systems"],
    "tpami": ["tpami", "pattern analysis and machine intelligence"],
    "tip": ["transactions on image processing"],
    "ieee access": ["ieee access"],
    "operations research": ["operations research"],
    "euro-par": ["euro-par", "parallel and distributed computing"],
}
TITLE_OK = 0.90


def bib_venue(fields: dict) -> tuple[str, str]:
    """(kind, text): kind in {'preprint', 'proceedings', 'journal', 'none'}"""
    for k in ("booktitle", "journal", "howpublished", "publisher"):
        v = strip_tex(fields.get(k, ""))
        if v:
            if "arxiv" in v.lower():
                return "preprint", v
            return ("proceedings" if k == "booktitle" else "journal"), v
    return "none", ""


def venue_tokens(text: str) -> list[str]:
    t = f" {text.lower()} "
    return [tok for tok, aliases in VENUES.items() if any(a in t for a in aliases)]


def resolve(entry: dict, arxiv_cache: dict) -> tuple[dict | None, str]:
    """Return (record, how)."""
    f = entry["fields"]
    aid = find_arxiv_id(f)
    if aid and aid in arxiv_cache:
        return arxiv_cache[aid], f"arXiv id {aid} (from bib field)"
    doi = find_doi(f)
    if doi:
        r = crossref_by_doi(doi)
        if r:
            return r, f"DOI {doi} (from bib field)"
    title = f.get("title", "")
    if not title:
        return None, "no title in entry"
    for name, fn in (("arXiv title search", arxiv_search_title), ("Crossref title search", crossref_search),
                     ("DBLP title search", dblp_search)):
        try:
            hits = fn(title)
        except Exception as e:  # network hiccup: keep going with the next source
            hits = []
            sys.stderr.write(f"  [{entry['key']}] {name} failed: {e}\n")
        best = max(hits, key=lambda r: title_ratio(title, r["title"]), default=None)
        if best and title_ratio(title, best["title"]) >= TITLE_OK:
            return best, f"{name} (ratio {title_ratio(title, best['title']):.2f})"
    return None, "not found on arXiv / Crossref / DBLP by title"


def evidence_strings(rec: dict) -> list[str]:
    out = []
    for k in ("comment", "journal_ref", "container", "event", "venue", "type"):
        if rec.get(k):
            out.append(f"{k}: {rec[k]}")
    return out


def check_entry(entry: dict, rec: dict | None, how: str, index_text: dict[str, str]) -> dict:
    f = entry["fields"]
    res = {"key": entry["key"], "type": entry["type"], "how": how, "verdict": "PASS", "problems": [], "notes": [],
           "source_url": rec["url"] if rec else "", "fix": {}}
    if rec is None:
        res["verdict"] = "FAIL"
        res["problems"].append("no matching record found -- treat as unverified / possibly hallucinated")
        return res
    # title
    tr = title_ratio(f.get("title", ""), rec["title"])
    res["title_ratio"] = round(tr, 3)
    if tr < TITLE_OK:
        res["verdict"] = "FAIL"
        res["problems"].append(f"title differs (ratio {tr:.2f}); record title: {rec['title']}")
        res["fix"]["title"] = rec["title"]
    elif tr < 0.98:
        res["notes"].append(f"title wording differs slightly from record: {rec['title']}")
    # authors
    bib_auth = split_bib_authors(f.get("author", ""))
    src_auth = rec.get("authors", [])
    if src_auth:
        cmp = compare_authors(bib_auth, src_auth)
        if len(bib_auth) == 1 and len(src_auth) > 10:
            res["notes"].append(f"collective author '{bib_auth[0]}' vs {len(src_auth)} listed authors; verify the style")
            if res["verdict"] == "PASS":
                res["verdict"] = "WARN"
        elif not cmp["ok"]:
            res["verdict"] = "FAIL"
            what = []
            if cmp["extra"]:
                what.append("names NOT in record (fabricated or misspelled): " + ", ".join(cmp["extra"]))
            if cmp["missing"]:
                what.append("record authors missing from bib: " + ", ".join(cmp["missing"]))
            if cmp["order_only"]:
                what.append("same names, different order")
            if not what:
                what.append(f"author count {cmp['n_bib']} vs record {cmp['n_src']}")
            res["problems"].append("authors: " + "; ".join(what))
            res["fix"]["author"] = " and ".join(src_auth)
        elif cmp["truncated"]:
            res["notes"].append(f"author list truncated with 'others' (record has {cmp['n_src']})")
    # year
    by, sy = re.sub(r"\D", "", f.get("year", "")), rec.get("year", "")
    if by and sy and by != sy:
        d = abs(int(by) - int(sy))
        print_version = bool(f.get("volume") or f.get("pages")) or f.get("journal", "").lower().find("arxiv") < 0 and bool(f.get("journal"))
        if d == 1:
            res["notes"].append(f"year {by} vs record {sy} (arXiv posting year; fine if the venue year is meant)")
        elif print_version:
            res["notes"].append(f"year {by} vs arXiv {sy}: journal print year may lag online / arXiv; confirm with the publisher record")
            if res["verdict"] == "PASS":
                res["verdict"] = "WARN"
        else:
            res["problems"].append(f"year {by} vs record {sy} (check)")
            res["verdict"] = "FAIL"
    # the authors' own bibtex inside the arXiv comment may list a different (venue-version) author set
    cm = rec.get("comment", "")
    if "author=" in cm.replace(" ", "") and src_auth:
        m = re.search(r"author\s*=\s*\{([^}]*)\}", cm)
        if m:
            venue_auth = split_bib_authors(m.group(1))
            if len(venue_auth) != len(src_auth):
                res["notes"].append(f"arXiv lists {len(src_auth)} authors but the authors' own bibtex in the comment lists "
                                    f"{len(venue_auth)}; cite the author list of the version you reference")
                if res["verdict"] == "FAIL" and compare_authors(bib_auth, venue_auth)["ok"]:
                    res["verdict"] = "WARN"
                    res["problems"] = [p for p in res["problems"] if not p.startswith("authors:")]
                    res["fix"].pop("author", None)
                    res["notes"].append("bib author list matches the venue-version bibtex from the arXiv comment")
    # venue
    kind, vtext = bib_venue(f)
    ev = evidence_strings(rec)
    ev_join = " | ".join(ev).lower()
    squash = lambda s: norm_title(s).replace(" ", "")  # 'Video-Gen' == 'VideoGen'
    idx_hits = [u for u, t in index_text.items()
                if squash(f.get("title", "")) in t.replace(" ", "") or squash(rec["title"]) in t.replace(" ", "")]
    res["venue_claim"] = f"{kind}: {vtext}" if vtext else "none"
    res["venue_evidence"] = ev + [f"index: {u}" for u in idx_hits]
    if kind in ("proceedings", "journal"):
        claimed = venue_tokens(vtext)
        confirmed = [tok for tok in claimed if tok in venue_tokens(ev_join) or idx_hits]
        if claimed and not confirmed:  # second opinion: Crossref / DBLP list the publication venue of indexed papers
            for name, fn, vkey in (("crossref", crossref_search, "container"), ("dblp", dblp_search, "venue")):
                try:
                    hits = fn(f.get("title", ""))
                except Exception as e:
                    res["notes"].append(f"{name} unreachable ({e.__class__.__name__})")
                    continue
                if not hits:
                    res["notes"].append(f"{name}: no title hit (or unreachable)")
                for h in hits:
                    if title_ratio(f.get("title", ""), h["title"]) >= TITLE_OK and (h.get(vkey) or h.get("event")):
                        vstr = " / ".join(x for x in (h.get(vkey), h.get("event")) if x)
                        res["venue_evidence"].append(f"{name}: {vstr} ({h['year']}) {h['url']}")
                        if any(tok in venue_tokens(vstr) for tok in claimed):
                            confirmed = claimed
                if confirmed:
                    break
        if "workshop" in ev_join and kind == "proceedings":
            res["problems"].append("record mentions a WORKSHOP; bib claims the main venue?")
            res["verdict"] = "FAIL" if not idx_hits else res["verdict"]
        found = venue_tokens(" | ".join(res["venue_evidence"]).lower())
        if claimed and not confirmed and found and not idx_hits:
            res["problems"].append(f"venue disagrees with the record: bib says '{vtext}', records say {', '.join(found).upper()}")
            res["verdict"] = "FAIL"
            res["fix"]["booktitle/journal"] = "; ".join(e for e in res["venue_evidence"] if any(a in e.lower() for t in found for a in VENUES[t]))
        elif claimed and not confirmed:
            where = f"; not found in the {len(index_text)} index page(s) given" if index_text else ""
            res["notes"].append(f"venue '{vtext}' not confirmed by arXiv / Crossref / DBLP records{where}; "
                                "check the proceedings index or OpenReview (workshop papers are NOT the main venue)")
            if res["verdict"] == "PASS":
                res["verdict"] = "WARN"
        elif not claimed:
            res["notes"].append(f"venue '{vtext}' not in the known list; confirm manually")
            if res["verdict"] == "PASS":
                res["verdict"] = "WARN"
    elif kind == "preprint":
        acc = re.search(r"(accepted|to appear|published|spotlight|oral)[^|]{0,80}", ev_join)
        submitted_only = "submitted" in ev_join and not acc
        if (acc or venue_tokens(ev_join)) and not submitted_only:
            res["notes"].append("record shows a publication venue; the preprint entry can be upgraded: " + "; ".join(ev)[:200])
            if res["verdict"] == "PASS":
                res["verdict"] = "WARN"
    else:
        res["notes"].append("entry has no venue field")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bib")
    ap.add_argument("--keys", nargs="*", help="only these keys (default: all)")
    ap.add_argument("--md", help="write a markdown report here")
    ap.add_argument("--json", help="write the full JSON report here")
    ap.add_argument("--index", action="append", default=[], help="proceedings index URL to grep titles in (repeatable)")
    a = ap.parse_args()

    entries = parse_bib(open(a.bib, encoding="utf-8", errors="replace").read())
    if a.keys:
        want = set(a.keys)
        entries = [e for e in entries if e["key"] in want]
        for k in want - {e["key"] for e in entries}:
            print(f"WARNING: key {k} not in {a.bib}", file=sys.stderr)
    ids = [find_arxiv_id(e["fields"]) for e in entries]
    ids = sorted({i for i in ids if i})
    print(f"{len(entries)} entries; {len(ids)} carry an arXiv id -> batch lookup", file=sys.stderr)
    arxiv_cache = arxiv_by_ids(ids) if ids else {}
    index_text = {}
    for u in a.index:
        try:
            index_text[u] = norm_title(html_to_text(polite_get(u, min_interval=1.0)))
            print(f"index {u}: {len(index_text[u])} chars", file=sys.stderr)
        except Exception as e:
            print(f"index {u}: fetch failed ({e})", file=sys.stderr)

    results = []
    for e in entries:
        rec, how = resolve(e, arxiv_cache)
        r = check_entry(e, rec, how, index_text)
        r["line"] = e["line"]
        results.append(r)
        flag = {"PASS": "  ", "WARN": "? ", "FAIL": "!!"}[r["verdict"]]
        print(f"{flag} {r['verdict']:4} {e['key']:<22} {how}", file=sys.stderr)
        for p in r["problems"]:
            print(f"        - {p}", file=sys.stderr)
        if r["verdict"] == "WARN":
            for n in r["notes"]:
                print(f"        - {n}", file=sys.stderr)

    lines = ["| key | verdict | matched via | problems | notes | evidence |", "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| `{r['key']}` | {r['verdict']} | {r['how']} | {'<br>'.join(r['problems']) or '-'} | "
                     f"{'<br>'.join(r['notes']) or '-'} | {'<br>'.join(r.get('venue_evidence', [])) or '-'} |")
    fixes = [r for r in results if r["fix"]]
    if fixes:
        lines += ["", "## Field values copied from the matched records (paste after checking)", ""]
        for r in fixes:
            lines.append(f"- `{r['key']}` ({r['source_url']}):")
            for k, v in r["fix"].items():
                lines.append(f"  - {k} = {{{v}}}")
    md = "\n".join(lines)
    print("\n" + md)
    if a.md:
        open(a.md, "w", encoding="utf-8").write(md + "\n")
    if a.json:
        json.dump(results, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    worst = max((r["verdict"] for r in results), key=["PASS", "WARN", "FAIL"].index, default="PASS")
    return {"PASS": 0, "WARN": 1, "FAIL": 2}[worst]


if __name__ == "__main__":
    sys.exit(main())
