#!/usr/bin/env python3
"""
verify.py — Check if references are real, find duplicates, validate citations.

Usage:
  python verify.py list < "refs.txt"
  python verify.py docx <path/to/thesis.docx>
  python verify.py doi 10.1000/example
  python verify.py pmid 12345678
"""
import argparse, json, os, re, sys, time, textwrap
from collections import defaultdict

INSTALLED = {"requests": False, "biopython": False, "semanticscholar": False, "docx": False}

try:
    import requests
    INSTALLED["requests"] = True
except ImportError:
    pass

try:
    from Bio import Entrez
    INSTALLED["biopython"] = True
    Entrez.email = "refcheck@local"
except ImportError:
    pass

try:
    from semanticscholar import SemanticScholar
    INSTALLED["semanticscholar"] = True
    _sch = SemanticScholar()
except ImportError:
    pass

try:
    from docx import Document
    INSTALLED["docx"] = True
except ImportError:
    pass

# ── helpers ──────────────────────────────────────────────

def doi_url(d):
    d = d.strip().rstrip(".,;)")
    if d.startswith("http"):
        m = re.search(r'(10\.\S+)', d)
        return m.group(1) if m else d
    return d

def extract_doi(text):
    m = re.search(r'(10\.\d{4,}/[^\s,;)]+)', text)
    return m.group(1) if m else None

def extract_pmid(text):
    m = re.search(r'\b(\d{8})\b', text)
    return m.group(1) if m else None

def clean(t):
    return re.sub(r'\s+', ' ', t).strip()

# ── verification sources ─────────────────────────────────

CACHE = {}

def check_crossref(doi):
    if doi in CACHE: return CACHE[doi]
    if not INSTALLED["requests"]: return None
    try:
        r = requests.get(f"https://api.crossref.org/works/{doi}",
                         headers={"User-Agent": "RefCheck/1.0"}, timeout=10)
        if r.status_code == 200:
            d = r.json()["message"]
            authors = [a.get("family","") for a in d.get("author",[])][:5]
            result = {
                "found": True,
                "source": "CrossRef",
                "title": (d.get("title") or [""])[0],
                "authors": ", ".join(authors),
                "year": (d.get("published-print") or d.get("issued") or {}).get("date-parts",[[None]])[0][0],
                "journal": (d.get("container-title") or [""])[0],
                "doi": doi,
            }
            CACHE[doi] = result
            return result
    except: pass
    CACHE[doi] = None
    return None

def check_pubmed(pmid=None, doi=None, title=None):
    if pmid and pmid in CACHE: return CACHE[pmid]
    if not INSTALLED["biopython"]: return None
    try:
        ids = []
        if pmid:
            ids = [pmid]
        elif doi:
            h = Entrez.esearch(db="pubmed", term=f"({doi}[DOI])", retmax=1, retmode="json")
            ids = json.load(h)["esearchresult"]["idlist"]
            h.close()
        elif title:
            h = Entrez.esearch(db="pubmed", term=title, retmax=3, retmode="json")
            ids = json.load(h)["esearchresult"]["idlist"]
            h.close()
        if not ids: return None
        h = Entrez.esummary(db="pubmed", id=",".join(ids[:3]), retmode="json")
        data = json.load(h)
        h.close()
        for uid in ids[:3]:
            rec = data["result"].get(uid)
            if rec:
                result = {
                    "found": True,
                    "source": "PubMed",
                    "pmid": uid,
                    "title": rec.get("title",""),
                    "authors": rec.get("authors","").split(", ")[:3],
                    "year": rec.get("pubdate","")[:4],
                    "journal": rec.get("source",""),
                    "doi": rec.get("elocationid","").replace("doi: ","") if "doi:" in rec.get("elocationid","") else None,
                }
                if pmid and CACHE.get(pmid) is None:
                    CACHE[pmid] = result
                return result
    except: pass
    return None

def check_semantic(title=None, doi=None):
    if not INSTALLED["semanticscholar"]: return None
    try:
        results = _sch.search_paper(doi or title, limit=3)
        for r in results:
            t = r.title.lower()[:60]
            if title and t != title.lower()[:60] and doi and r.externalIds.get("DOI","") != doi:
                continue
            return {
                "found": True,
                "source": "Semantic Scholar",
                "title": r.title,
                "authors": ", ".join(a.name for a in r.authors[:5]),
                "year": r.year,
                "doi": r.externalIds.get("DOI",""),
                "url": r.url or f"https://www.semanticscholar.org/paper/{r.paperId}",
            }
        if title:
            return {"found": False, "source": "Semantic Scholar", "note": "No exact title match"}
    except: pass
    return None

def verify_ref(ref):
    """Try CrossRef → PubMed → Semantic Scholar for one reference dict."""
    doi = ref.get("doi") or extract_doi(ref.get("raw",""))
    pmid = ref.get("pmid")
    title = ref.get("title","")
    authors = ref.get("authors","")

    result = ref.copy()

    # Try DOI → CrossRef first
    if doi:
        cr = check_crossref(doi)
        if cr:
            result.update(cr)
            return result
        # DOI didn't resolve → try PubMed
        pm = check_pubmed(doi=doi)
        if pm:
            result.update(pm)
            return result

    # Try PMID
    if pmid:
        pm = check_pubmed(pmid=pmid)
        if pm:
            result.update(pm)
            return result

    # Try title
    if title:
        pm = check_pubmed(title=title)
        if pm:
            result.update(pm)
            return result
        ss = check_semantic(title=title)
        if ss and ss.get("found"):
            result.update(ss)
            return result

    result.update({"found": False, "source": "none"})
    return result

# ── reference parsing ────────────────────────────────────

def parse_ref_text(text):
    """Parse a blob of reference text into individual references."""
    refs = []
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]

    # If every line is a DOI or PMID (short entries) → one per line
    if all(len(l) < 80 and (extract_doi(l) or extract_pmid(l) or l.startswith('10.')) for l in lines):
        for i, line in enumerate(lines):
            ref = {"num": i+1, "raw": line}
            ref["doi"] = extract_doi(line)
            ref["pmid"] = extract_pmid(line)
            refs.append(ref)
        return refs

    # Try numbered list: [1] or 1.
    parts = re.split(r'\n\s*(?=\[?\d+\][.\s])', text.strip())
    if len(parts) < 2:
        # Try author-year style
        parts = re.split(r'\n\s*(?=[A-Z][a-z]+,\s)', text.strip())
    if len(parts) < 2:
        parts = [text.strip()]

    for i, part in enumerate(parts):
        part = part.strip()
        if not part: continue
        # Remove leading number
        part = re.sub(r'^\[?\d+\]?[.\s]*', '', part)
        ref = {"num": i+1, "raw": part}
        ref["doi"] = extract_doi(part)
        ref["pmid"] = extract_pmid(part)
        lines = part.split(". ")
        if len(lines) >= 2:
            ref["title"] = clean(lines[1]) if len(lines) > 1 else ""
            ref["authors"] = clean(lines[0])
            m = re.search(r'\b((?:19|20)\d{2})\b', part)
            ref["year"] = m.group(1) if m else None
        refs.append(ref)
    return refs

def extract_from_docx(path):
    """Extract references and in-text citations from a .docx thesis."""
    if not INSTALLED["docx"]:
        return {"error": "python-docx not installed"}, [], []

    doc = Document(path)
    full_text = "\n".join(p.text for p in doc.paragraphs)

    # Find reference section
    ref_section = ""
    for p in doc.paragraphs:
        txt = p.text.strip().lower()
        if any(kw in txt for kw in ["references", "bibliography", "works cited"]):
            # Start collecting from this paragraph
            started = False
            for pp in doc.paragraphs:
                if pp.text.strip().lower().startswith(tuple(["references", "bibliography", "works cited"])):
                    if started:
                        ref_section += pp.text + "\n"
                    else:
                        started = True
                elif started and len(pp.text.strip()) > 20:
                    ref_section += pp.text + "\n"
                elif started and len(pp.text.strip()) == 0:
                    break
            break

    if not ref_section:
        ref_section = full_text

    refs = parse_ref_text(ref_section)

    # Extract in-text citations
    citations = re.findall(r'\([^)]*\d{4}[^)]*\)', full_text)
    seen = set()
    unique_cites = []
    for c in citations:
        if c not in seen:
            seen.add(c)
            unique_cites.append(c)

    return {"title": doc.core_properties.title or ""}, refs, unique_cites

# ── duplicates ───────────────────────────────────────────

def find_duplicates(refs):
    dupes = []
    for i, a in enumerate(refs):
        for j, b in enumerate(refs):
            if j <= i: continue
            score = 0
            if a.get("doi") and a["doi"] == b.get("doi"): score = 100
            elif a.get("year") and a["year"] == b.get("year"):
                a_auth = a.get("authors","")[:20].lower()
                b_auth = b.get("authors","")[:20].lower()
                if a_auth and b_auth and a_auth == b_auth: score = 90
            if score >= 80:
                dupes.append((i+1, j+1, score))
    return dupes

# ── citation–reference matching ──────────────────────────

def match_citations_to_refs(citations, refs):
    """Check which in-text citations have matching reference entries."""
    unmatched = []
    for cite in citations:
        # Extract author name + year from citation
        m = re.search(r'([A-Z][a-z]+(?:\s+(?:et\s+al\.?|&\s+[A-Z][a-z]+))?)[,\s]+((?:19|20)\d{2})', cite)
        if not m:
            unmatched.append({"citation": cite, "reason": "Could not parse author+year"})
            continue
        cite_auth = m.group(1).split(",")[0].strip().lower().split()[-1]
        cite_year = m.group(2)

        matched = False
        for ref in refs:
            ref_auth = (ref.get("authors","") or "").split(",")[0].strip().lower()
            if ref_auth and cite_auth in ref_auth and ref.get("year") == cite_year:
                matched = True
                break

        if not matched:
            unmatched.append({"citation": cite, "reason": f"No reference entry for {cite_auth} {cite_year}"})

    return unmatched

# ── report ───────────────────────────────────────────────

def format_report(meta, refs, dupes, unmatched, results):
    lines = []
    lines.append("# Reference Audit Report")
    lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M')}")
    if meta.get("title"):
        lines.append(f"**Document:** {meta['title']}")
    lines.append(f"**Total references:** {len(refs)}")
    lines.append("")

    # Summary
    real = sum(1 for r in results if r.get("found"))
    fake = sum(1 for r in results if not r.get("found"))
    lines.append(f"## Summary")
    lines.append(f"- ✅ Confirmed real: **{real}**")
    lines.append(f"- ❌ Not found (suspicious): **{fake}**")
    lines.append(f"- 🔁 Duplicate pairs: **{len(dupes)}**")
    lines.append(f"- ⚠️ Unmatched citations: **{len(unmatched)}**")
    lines.append("")

    # Suspicious
    suspicious = [r for r in results if not r.get("found")]
    if suspicious:
        lines.append("## ❌ Potentially Fake/Hallucinated References")
        lines.append("| # | Raw text | Reason |")
        lines.append("|---|----------|--------|")
        for r in suspicious:
            raw = r.get("raw","")[:60]
            lines.append(f"| {r['num']} | {raw}... | Not found in CrossRef/PubMed/Semantic Scholar |")
        lines.append("")

    # Duplicates
    if dupes:
        lines.append("## 🔁 Duplicate References")
        lines.append("| Entry A | Entry B | Confidence |")
        lines.append("|---------|---------|------------|")
        for i, j, score in dupes:
            lines.append(f"| #{i} | #{j} | {score}% |")
        lines.append("")

    # Unmatched citations
    if unmatched:
        lines.append("## ⚠️ In-Text Citations Without Matching Reference")
        for u in unmatched:
            lines.append(f"- `{u['citation']}` → {u['reason']}")
        lines.append("")

    # Full table
    lines.append("## 📋 All References")
    lines.append("| # | Reference | Status | Source | DOI/PMID |")
    lines.append("|---|-----------|--------|--------|----------|")
    for r in results:
        status = "✅" if r.get("found") else "❌"
        src = r.get("source","") or "-"
        doi = r.get("doi","") or "-"
        raw = r.get("raw","")[:50]
        lines.append(f"| {r['num']} | {raw}... | {status} | {src} | {doi} |")
    lines.append("")

    return "\n".join(lines)

# ── main ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Verify references against real databases")
    sub = parser.add_subparsers(dest="mode")

    p_list = sub.add_parser("list", help="Check a list of references from stdin")
    p_list.add_argument("--out", help="Output path for report")

    p_docx = sub.add_parser("docx", help="Extract and verify from .docx file")
    p_docx.add_argument("path", help="Path to .docx file")
    p_docx.add_argument("--out", help="Output path for report")

    p_doi = sub.add_parser("doi", help="Check a single DOI")
    p_doi.add_argument("doi")
    p_doi.add_argument("--out")

    p_pmid = sub.add_parser("pmid", help="Check a single PMID")
    p_pmid.add_argument("pmid")
    p_pmid.add_argument("--out")

    args = parser.parse_args()
    if not args.mode:
        parser.print_help()
        return

    # Parse input
    meta = {}
    refs = []

    if args.mode == "doi":
        refs = [{"num": 1, "raw": args.doi, "doi": args.doi}]
    elif args.mode == "pmid":
        refs = [{"num": 1, "raw": args.pmid, "pmid": args.pmid}]
    elif args.mode == "list":
        text = sys.stdin.read()
        refs = parse_ref_text(text)
    elif args.mode == "docx":
        meta, refs, citations = extract_from_docx(args.path)
        if "error" in meta:
            print(json.dumps({"error": meta["error"]}))
            return

    sys.stderr.write(f"Verifying {len(refs)} references...\n")

    # Verify each reference
    results = []
    for ref in refs:
        result = verify_ref(ref)
        results.append(result)
        mark = '✅' if result.get('found') else '❌'
        raw = result.get('raw','')[:50].replace('\n',' ')
        sys.stderr.write(f"  [{result['num']}] {mark} {raw}\n")
        time.sleep(0.5)  # rate limit

    # Check duplicates
    dupes = find_duplicates(refs)

    # Match citations to refs (only for docx mode)
    unmatched = []
    if args.mode == "docx":
        unmatched = match_citations_to_refs(citations, refs)

    # Generate report
    report = format_report(meta, refs, dupes, unmatched, results)

    out = args.out or "refcheck_report.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport saved to: {out}")
    print(report)

if __name__ == "__main__":
    main()
