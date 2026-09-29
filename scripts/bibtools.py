"""Shared helpers for the CiteWitness skill: a small BibTeX parser, string normalisation and
fetchers for arXiv / Crossref / DBLP.  Standard library only (urllib, json, xml).  Every fetch goes over https.

Nothing in this module invents bibliographic data: every returned record carries the URL it came from.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

UA = "CiteWitness/1.0 (python-urllib; academic citation audit)"
ARXIV_ID_RE = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(v\d+)?(?![\d.])")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>{},]+")
_LAST_CALL: dict[str, float] = {}


def polite_get(url: str, min_interval: float = 1.0, timeout: int = 60) -> bytes:
    """GET with a per-host minimum interval (arXiv asks for ~3 s between requests)."""
    host = urllib.parse.urlparse(url).netloc
    wait = _LAST_CALL.get(host, 0) + min_interval - time.time()
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    finally:
        _LAST_CALL[host] = time.time()
    return data


# ---------------------------------------------------------------- BibTeX parsing
def _matching_brace(s: str, i: int) -> int:
    """s[i] == '{'; return index of the matching '}'."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    raise ValueError("unbalanced braces in bib file")


def _parse_fields(body: str) -> dict:
    fields: dict[str, str] = {}
    i, n = 0, len(body)
    while i < n:
        m = re.match(r"\s*([\w\-:]+)\s*=\s*", body[i:])
        if not m:
            nxt = body.find(",", i)
            if nxt < 0:
                break
            i = nxt + 1
            continue
        name = m.group(1).lower()
        i += m.end()
        if i >= n:
            break
        if body[i] == "{":
            j = _matching_brace(body, i)
            val, i = body[i + 1:j], j + 1
        elif body[i] == '"':
            j = i + 1
            while j < n and (body[j] != '"' or body[j - 1] == "\\"):
                j += 1
            val, i = body[i + 1:j], j + 1
        else:  # bare number or macro
            j = i
            while j < n and body[j] not in ",\n":
                j += 1
            val, i = body[i:j].strip(), j
        fields[name] = " ".join(val.split())
        nxt = body.find(",", i)
        if nxt < 0:
            break
        i = nxt + 1
    return fields


def parse_bib(text: str) -> list[dict]:
    """Return [{type, key, fields, raw, line}] for every @entry (comments and @comment/@string skipped)."""
    entries = []
    i = 0
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        line_start = text.rfind("\n", 0, at) + 1
        if "%" in text[line_start:at]:  # '@' inside a comment line
            i = at + 1
            continue
        m = re.match(r"@(\w+)\s*\{", text[at:])
        if not m:
            i = at + 1
            continue
        open_i = at + m.end() - 1
        close_i = _matching_brace(text, open_i)
        etype = m.group(1).lower()
        body = text[open_i + 1:close_i]
        i = close_i + 1
        if etype in ("comment", "preamble", "string"):
            continue
        key, _, rest = body.partition(",")
        entries.append({"type": etype, "key": key.strip(), "fields": _parse_fields(rest),
                        "raw": text[at:close_i + 1], "line": text.count("\n", 0, at) + 1})
    return entries


# ---------------------------------------------------------------- normalisation
def strip_tex(s: str) -> str:
    s = re.sub(r"\\[a-zA-Z]+\s*", " ", s)  # \emph, \textbf, \log ...
    s = s.replace("{", "").replace("}", "").replace("$", "").replace("~", " ")
    s = s.replace("--", "-").replace("\\", "")
    return " ".join(s.split())


def ascii_fold(s: str) -> str:
    s = re.sub(r"\\[`'^\"~=.uvHtcdb]\{?(\w)\}?", r"\1", s)  # \'{e} -> e
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def norm_title(s: str) -> str:
    s = ascii_fold(strip_tex(s)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(s.split())


def title_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_title(a), norm_title(b)).ratio()


def split_bib_authors(field: str) -> list[str]:
    """'Last, First and First Last and others' -> ['First Last', ...]; 'others' kept as literal marker."""
    out = []
    for a in re.split(r"\s+and\s+", strip_tex(field)):
        a = a.strip()
        if not a:
            continue
        if a.lower() == "others":
            out.append("others")
            continue
        if "," in a:
            last, _, first = a.partition(",")
            a = f"{first.strip()} {last.strip()}".strip()
        out.append(" ".join(a.split()))
    return out


def surname(full_name: str) -> str:
    """Last token, ASCII-folded, lower-case; ignores 'Jr.' / 'III'."""
    toks = [t for t in ascii_fold(full_name).replace(".", ". ").split() if t.lower().strip(".,") not in ("jr", "iii", "ii")]
    return re.sub(r"[^a-z\-']", "", toks[-1].lower()) if toks else ""


def compare_authors(bib_authors: list[str], src_authors: list[str]) -> dict:
    """Compare surname sequences.  Handles a trailing 'others' in the bib list (prefix comparison)."""
    truncated = bool(bib_authors) and bib_authors[-1] == "others"
    bib = [surname(a) for a in bib_authors if a != "others"]
    src = [surname(a) for a in src_authors]
    src_cmp = src[:len(bib)] if truncated else src
    return {
        "ok": bib == src_cmp,
        "truncated": truncated,
        "missing": [a for a, s in zip(src_authors, src) if s not in bib and not (truncated and s not in src_cmp)],
        "extra": [a for a, s in zip([x for x in bib_authors if x != "others"], bib) if s not in src],
        "order_only": sorted(bib) == sorted(src_cmp) and bib != src_cmp,
        "n_bib": len(bib), "n_src": len(src),
    }


# ---------------------------------------------------------------- arXiv
_NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}


def _arxiv_entries(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall("a:entry", _NS):
        aid_full = e.find("a:id", _NS).text.strip().split("/abs/")[-1]
        title_el = e.find("a:title", _NS)
        if title_el is None or title_el.text is None or "Error" in aid_full:
            continue
        get = lambda tag: (e.find(tag, _NS).text.strip() if e.find(tag, _NS) is not None and e.find(tag, _NS).text else "")
        out.append({
            "source": "arxiv", "id": re.sub(r"v\d+$", "", aid_full), "id_versioned": aid_full,
            "title": " ".join(title_el.text.split()),
            "authors": [a.find("a:name", _NS).text.strip() for a in e.findall("a:author", _NS)],
            "published": get("a:published")[:10], "year": get("a:published")[:4],
            "comment": " ".join(get("x:comment").split()), "journal_ref": " ".join(get("x:journal_ref").split()),
            "doi": get("x:doi"), "url": f"https://arxiv.org/abs/{re.sub(r'v\\d+$', '', aid_full)}",
        })
    return out


def arxiv_by_ids(ids: list[str]) -> dict[str, dict]:
    """Batch metadata lookup; returns {id_without_version: record}."""
    recs: dict[str, dict] = {}
    ids = [re.sub(r"v\d+$", "", i) for i in ids]
    for k in range(0, len(ids), 40):
        chunk = ids[k:k + 40]
        url = f"https://export.arxiv.org/api/query?id_list={','.join(chunk)}&max_results={len(chunk)}"
        for r in _arxiv_entries(polite_get(url, min_interval=3.0)):
            recs[r["id"]] = r
    return recs


def arxiv_search_title(title: str, max_results: int = 5) -> list[dict]:
    q = urllib.parse.quote(f'ti:"{norm_title(title)}"')
    url = f"https://export.arxiv.org/api/query?search_query={q}&max_results={max_results}"
    return _arxiv_entries(polite_get(url, min_interval=3.0))


# ---------------------------------------------------------------- Crossref
def _crossref_record(it: dict) -> dict:
    issued = (it.get("issued") or {}).get("date-parts") or [[None]]
    authors = []
    for a in it.get("author", []) or []:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name", "")
        authors.append(name)
    return {
        "source": "crossref", "doi": it.get("DOI", ""), "title": " ".join((it.get("title") or [""])[0].split()),
        "authors": authors, "year": str(issued[0][0]) if issued and issued[0] and issued[0][0] else "",
        "container": " ".join((it.get("container-title") or [""])[0].split()),
        "event": (it.get("event") or {}).get("name", ""), "type": it.get("type", ""),
        "volume": it.get("volume", ""), "issue": it.get("issue", ""), "pages": it.get("page", ""),
        "url": f"https://doi.org/{it.get('DOI', '')}",
    }


def crossref_by_doi(doi: str) -> dict | None:
    try:
        data = json.loads(polite_get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}", min_interval=1.0))
    except Exception:
        return None
    return _crossref_record(data["message"])


def crossref_search(title: str, rows: int = 5) -> list[dict]:
    url = f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(strip_tex(title))}&rows={rows}"
    data = json.loads(polite_get(url, min_interval=1.0))  # network errors propagate: callers report "unreachable"
    return [_crossref_record(it) for it in data["message"]["items"]]


def crossref_bibtex(doi: str) -> str:
    return polite_get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}/transform/application/x-bibtex",
                      min_interval=1.0).decode("utf-8", "replace")


# ---------------------------------------------------------------- DBLP
def dblp_search(title: str, hits: int = 5) -> list[dict]:
    url = f"https://dblp.org/search/publ/api?q={urllib.parse.quote(strip_tex(title))}&format=json&h={hits}"
    data = json.loads(polite_get(url, min_interval=1.0, timeout=30))  # network errors propagate
    out = []
    for h in (data.get("result", {}).get("hits", {}).get("hit") or []):
        info = h.get("info", {})
        au = info.get("authors", {}).get("author", [])
        if isinstance(au, dict):
            au = [au]
        out.append({"source": "dblp", "key": info.get("key", ""), "title": " ".join(info.get("title", "").rstrip(".").split()),
                    "authors": [re.sub(r"\s\d{4}$", "", a.get("text", "")) for a in au], "year": info.get("year", ""),
                    "venue": info.get("venue", "") if isinstance(info.get("venue", ""), str) else " / ".join(info.get("venue", [])),
                    "type": info.get("type", ""), "url": info.get("ee", "") or f"https://dblp.org/rec/{info.get('key', '')}"})
    return out


def dblp_bibtex(key: str) -> str:
    return polite_get(f"https://dblp.org/rec/{key}.bib?param=1", min_interval=1.0).decode("utf-8", "replace")


# ---------------------------------------------------------------- misc
def find_arxiv_id(fields: dict) -> str | None:
    for k in ("eprint", "arxivid", "note", "journal", "url", "howpublished", "doi", "volume"):
        v = fields.get(k, "")
        m = ARXIV_ID_RE.search(v)
        if m:
            return m.group(1)
    return None


def find_doi(fields: dict) -> str | None:
    for k in ("doi", "url", "note"):
        m = DOI_RE.search(fields.get(k, ""))
        if m:
            return m.group(0).rstrip(".")
    return None


def html_to_text(raw: bytes) -> str:
    import html as _html
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return " ".join(_html.unescape(t).split())
