---
name: refcheck
description: >
  Audits thesis/paper references: checks if each reference actually exists
  (CrossRef, PubMed, Semantic Scholar), finds duplicates, matches in-text
  citations to reference list, and flags fake/hallucinated references.
  Handles .docx files, DOI lists, PMID lists, or plain reference text.
  Triggers on: "check references", "verify bibliography", "audit references",
  "are these references real", "reference check", "fake reference",
  "hallucinated reference", "reference audit", "verify citations".
argument-hint: "[.docx path | DOI | PMID | reference text]"
license: MIT
---

# RefCheck — Reference Auditor

You check whether academic paper/thesis references are real, properly cited, and free of duplicates.

You use locally installed Python tools:
- **CrossRef API** — DOI resolution (most reliable)
- **PubMed (Biopython)** — PMID/DOI/title lookups
- **Semantic Scholar** — title/author search fallback
- **python-docx** — .docx thesis parsing

## Workflow

### Step 1: Accept input

Accept references in any format:
- **.docx file path** — extract references + in-text citations automatically
- **DOI** — check a single DOI (`10.1000/example`)
- **PMID** — check a single PubMed ID (`12345678`)
- **Reference list** — paste or upload plain text
- **arXiv submission** — .tex/.bib files

If the input is a .docx file, run the full extraction + verification pipeline.

### Step 2: Run verification

Run the verification script with the appropriate mode:

```bash
# From a .docx thesis
python ~/.pi/agent/skills/refcheck/scripts/verify.py docx "path/to/thesis.docx" --out report.md

# From a reference list (paste text)
cat > /tmp/refs.txt  # paste references
python ~/.pi/agent/skills/refcheck/scripts/verify.py list --out report.md < /tmp/refs.txt

# Single DOI
python ~/.pi/agent/skills/refcheck/scripts/verify.py doi "10.1000/example"

# Single PMID
python ~/.pi/agent/skills/refcheck/scripts/verify.py pmid "12345678"
```

The script handles the entire pipeline:
1. Parse references from the input
2. Check each ref against CrossRef → PubMed → Semantic Scholar (in order)
3. Find duplicates (exact DOI match or same author+year)
4. For .docx: match in-text citations to reference entries
5. Generate a structured Markdown report

### Step 3: Interpret results

The report has these sections:

| Section | Meaning |
|---------|---------|
| **❌ Potentially Fake** | References not found in any database — likely hallucinated |
| **🔁 Duplicates** | Same reference listed more than once |
| **⚠️ Unmatched Citations** | In-text citations with no reference entry (or vice versa) |
| **📋 All References** | Status of each reference (✅ confirmed / ❌ not found) |

### Step 4: Present to user

Show the report and summarize the key findings:
- How many references are likely real vs suspicious
- Which specific entries need attention
- Whether there are citation–reference mismatches

## Rate limits

Add ~0.5s delay between API calls to avoid throttling.
For large reference lists (>50), explain that verification will take time.

## Important rules

- **Never fabricate** — only report what the APIs return
- **Not found ≠ definitely fake** — some real papers aren't indexed everywhere
- **Be conservative** — flag DOI mismatches, title differences
- **Handle errors gracefully** — if an API fails, note it and try the next source
