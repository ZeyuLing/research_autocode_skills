# Full-text citation and bibliography audit

Use this protocol in every initial review and independent re-review. R4 owns it for a doctoral thesis; R3 owns it for a master's thesis. The objective is to verify every use of external evidence, not merely whether citation keys compile.

## 1. Scope and evidence boundary

Audit all active citation occurrences in the frozen thesis, including citations in abstracts, chapters, captions, tables, footnotes, appendices, and author/publication material when they make scholarly claims. Exclude inactive source branches and comments, but record how active files were determined.

Treat one occurrence with multiple cited keys as multiple **citation--source pairs**. Repeated uses of the same source remain separate pairs because different sentences may make different claims. Audit every cited bibliography entry; inventory uncited entries separately without automatically treating them as defects.

In an isolated blind-review round, use only the thesis, its bibliography, and public sources reachable from the citations. Do not use private companion papers, internal repositories, logs, or author declarations before the reviewer verdict is frozen. Later author-side checks must be labeled provenance audit.

## 2. Build the inventory

Create `03-citation-audit-ledger.md` and record:

- frozen PDF checksum, source commit, review date, and active source roots;
- number of active citation commands/occurrences;
- number of citation--source pairs after expanding clusters;
- number of unique cited keys and bibliography entries;
- missing keys, duplicate keys, uncited entries, unresolved citations, and bibliography parse limitations.

Use one row per citation--source pair:

| Occurrence ID | PDF/source location | Exact attached proposition | Cite key | Public source/identifier | Source opened | Support | Metadata/status | Severity/finding | Disposition/evidence |
|---|---|---|---|---|---|---|---|---|---|

Use stable occurrence IDs in reading order. For a citation cluster, repeat the occurrence ID for each key. The exact proposition must state what the thesis asks that source to support; do not copy an entire paragraph when only one clause is attached.

## 3. Static closure checks

Before semantic verification, check the complete active corpus:

1. every cited key resolves to exactly one bibliography entry;
2. there are no duplicate-key collisions or unresolved citation markers;
3. titles, authors, year, venue or document type, pages where applicable, DOI/arXiv/URL, and access date where required are present and normalized under the governing style;
4. preprint, accepted, in-press, and published status are not conflated;
5. retractions, withdrawals, expressions of concern, errata, and superseding versions are recorded when material;
6. datasets, software, standards, laws, websites, and repositories cite the appropriate primary artifact rather than an unrelated secondary paper;
7. self-citations and publications listed in the CV use accurate authorship and status.

Static closure is necessary but not sufficient. A clean BibTeX build does not establish that a source supports the sentence citing it.

## 4. Verify every citation occurrence semantically

For every citation--source pair:

1. identify the smallest exact proposition attached to the citation;
2. open the cited primary source or an authoritative official record; use the version that matches the bibliography and frozen review date;
3. verify the proposition against the source's actual task, assumptions, method, data, protocol, result, and conclusion;
4. distinguish what the source directly states from the thesis author's inference;
5. check that a survey or secondary source is not being used to launder a stronger claim than its primary evidence supports;
6. for clusters, determine what each source contributes; do not allow one relevant paper to mask unrelated padding;
7. for comparisons or priority claims such as “first,” “most,” “state of the art,” “widely used,” or “few studies,” verify the search/date boundary or require narrower wording;
8. for quotations, definitions, numerical values, dataset statistics, policy rules, and attributed limitations, verify exactness and context;
9. for inaccessible sources, record the attempted persistent identifier or official endpoint and classify the row as `unverifiable`, never silently `verified`.

Assign one support status:

- `direct` — the source directly supports the attached proposition in the stated context;
- `partial` — only part of the proposition or a narrower version is supported;
- `context-only` — relevant background, but not evidence for the attached factual or comparative claim;
- `mismatch` — the source contradicts or does not support the proposition;
- `unverifiable` — the source could not be accessed or identified sufficiently;
- `not-needed` — the citation is attached to author reasoning that does not require external attribution; retain only with an explicit reason.

Do not infer support from title similarity, abstract keywords, citation count, venue reputation, or another paper's reference list. Avoid excessive quotation; record a concise paraphrase and a precise page, section, theorem, table, or official metadata endpoint where possible.

## 5. Finding calibration

Apply the ordinary five-question finding test and minimum sufficient remedy.

- `S0`: fabricated/nonexistent source, systematic deceptive attribution, or citation conduct that creates a substantiated integrity blocker.
- `S1`: an unsupported or misrepresented source is indispensable to a central novelty, correctness, dataset, safety, or thesis-level conclusion.
- `S2`: a material related-work, method, data, protocol, or result claim is only partially supported or omits a decisive source, but can be repaired without overturning the thesis.
- `S3`: local missing citation, ambiguous placement, metadata/status error, irrelevant cluster member, or formatting inconsistency.
- `S4`: optional source enrichment that is not necessary for correctness or fair positioning.

Prefer repairing the sentence, moving the citation, splitting a compound claim, adding the correct primary source, or correcting metadata. Do not demand new experiments merely because a citation is weak.

## 6. Completion and re-review gate

The citation audit passes only when:

- ledger occurrence counts reconcile with the active source/PDF inventory;
- every citation--source pair has a non-empty support status and disposition;
- every unique cited entry has a metadata/publication-status disposition;
- every missing, partial, context-only, mismatch, or unverifiable row is linked to a finding, an explicit question, or a reasoned non-finding;
- no row remains `pending`, `unchecked`, or silently omitted;
- the citation-owning reviewer reports counts and limitations in the independent report.

After citation, claim, related-work, bibliography, status, dataset-source, or attribution edits, regenerate the complete ledger. Recheck every changed occurrence and every other occurrence that reuses the affected source. A previous 100 percent ledger does not carry over to a new frozen PDF or commit.
