# Full-text citation and bibliography audit

Use this protocol in every initial review and independent re-review. R4 owns it for a doctoral thesis; R3 owns it for a master's thesis. The objective is to verify every use of external evidence, not merely whether citation keys compile.

## 1. Scope and evidence boundary

Audit all active citation occurrences in the frozen thesis, including citations in abstracts, chapters, captions, tables, footnotes, appendices, and author/publication material when they make scholarly claims. Exclude inactive source branches and comments, but record how active files were determined.

Treat one occurrence with multiple cited keys as multiple **citation--source pairs**. Repeated uses of the same source remain separate pairs because different sentences may make different claims. Audit every cited bibliography entry; inventory uncited entries separately without automatically treating them as defects.

In an isolated blind-review round, use only the thesis, its bibliography, and public sources reachable from the citations. Do not use private companion papers, internal repositories, logs, or author declarations before the reviewer verdict is frozen. Later author-side checks must be labeled provenance audit.

## 2. Build the two-part inventory

Create `03-citation-audit-ledger.md` and record:

- frozen PDF checksum, source commit, review date, and active source roots;
- number of active citation commands/occurrences;
- number of citation--source pairs after expanding clusters;
- number of unique cited keys and bibliography entries, including uncited entries;
- missing keys, duplicate keys, uncited entries, unresolved citations, and bibliography parse limitations.

First create a **bibliography master table** with exactly one row per BibTeX/bibliography entry, including uncited entries:

| Bib key | Cited? | Type | Title verdict | Ordered authors verdict | Year verdict | Venue and publication/acceptance-status verdict | Pages/article-number verdict | DOI/arXiv/URL verdict | Authoritative record(s) opened | Existence/integrity verdict | Finding/disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|

Each field verdict must be `exact`, `mismatch`, `legitimate N/A`, or `unverifiable`; do not collapse all metadata into one check mark. Record both the thesis value and the verified canonical value whenever they differ. Style-required capitalization, name abbreviation, or punctuation normalization is not a factual mismatch, but changed title content, omitted/reordered authors, wrong year, false venue/status, and wrong pages or article number are factual mismatches.

Then create a **citation-occurrence table** with one row per citation--source pair:

| Occurrence ID | PDF/source location | Exact attached proposition | Cite key | Public source/identifier | Source opened | Support | Metadata/status | Severity/finding | Disposition/evidence |
|---|---|---|---|---|---|---|---|---|---|

Use stable occurrence IDs in reading order. For a citation cluster, repeat the occurrence ID for each key. The exact proposition must state what the thesis asks that source to support; do not copy an entire paragraph when only one clause is attached.

## 3. Static closure checks

Before semantic verification, check the complete active corpus:

1. every cited key resolves to exactly one bibliography entry;
2. there are no duplicate-key collisions or unresolved citation markers;
3. every title matches the authoritative title in content, including subtitle when part of the official record;
4. every author is present in the official order; do not store `et al.` as the BibTeX author list or silently omit consortium/corporate authors;
5. the year follows the governing style's event/proceedings/issue rule and does not confuse online-first, preprint-upload, acceptance, conference, or issue year;
6. venue and status are verified separately: `published`, `accepted/in press`, `preprint`, `submitted/under review`, `withdrawn/retracted/corrected`, or `unverifiable`; an arXiv posting, project page, code repository, author CV, or search snippet does not by itself prove conference/journal acceptance;
7. journal volume/issue and page range or article number, and proceedings page range where assigned, match the official record; use `legitimate N/A` for arXiv-only and genuinely pageless records rather than inventing pages;
8. DOI, arXiv identifier/version, URL, ISBN or other persistent identifier resolves to the same title and authors rather than merely returning a live page;
9. access dates required for mutable web resources are present and defensible;
10. retractions, withdrawals, expressions of concern, errata, and superseding versions are recorded when material;
11. datasets, software, standards, laws, websites, and repositories cite the appropriate primary artifact rather than an unrelated secondary paper;
12. self-citations and publications listed in the CV use accurate authorship and status.

Static closure is necessary but not sufficient. A clean BibTeX build does not establish that a source supports the sentence citing it.

### Authoritative-source order for bibliography fields

Use the strongest available record and record the exact endpoint opened:

1. publisher/DOI landing page, official journal issue, or official conference proceedings paper page/PDF;
2. official conference accepted-paper list or program for an accepted but not yet published paper;
3. official preprint record such as arXiv for preprint identity and version only;
4. Crossref and DBLP as structured corroboration, not as substitutes when a first-party record is available;
5. institutional repository or author page only as secondary evidence.

Search-result snippets, generated citation sites, Semantic Scholar/OpenAlex-style aggregators, code README files, and another paper's bibliography are discovery aids, not final authority. If no first-party record is accessible, require two independent corroborating records where feasible and mark the field `unverifiable` rather than guessing.

For `accepted/in press`, require an official accepted-paper list, publisher forthcoming record, DOI/proceedings record, or an acceptance document supplied in the separately labeled author-side lane. Do not upgrade `submitted`, `under review`, or `arXiv preprint` to accepted/published from author assertion alone in the blind-review lane.

### Fabricated or nonexistent citation escalation

Open an integrity investigation when any of the following occurs:

- the DOI or persistent identifier resolves to a different title or author set;
- the claimed proceedings volume/page range belongs to another paper;
- the official journal issue, proceedings, or accepted-paper list affirmatively contradicts the claimed venue/status;
- the entry combines a title, author list, venue, year, or pages from different works;
- exact-title, author-title, identifier, and official venue searches all fail and an authoritative record indicates the claimed work does not exist.

Do not label a paywalled, obscure, future, private, or temporarily inaccessible work fabricated solely because it was not found quickly. Record search routes and negative evidence. A substantiated fabricated/nonexistent citation is `S0` and blocks a `ready` verdict until resolved; an unresolved existence concern remains an explicit high-priority question or finding according to the available affirmative evidence.

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

- the bibliography master table has exactly one row per bibliography entry, including uncited entries;
- every mandatory bibliography field has an `exact`, `mismatch`, `legitimate N/A`, or `unverifiable` verdict and an authoritative evidence endpoint;
- ledger occurrence counts reconcile with the active source/PDF inventory;
- every citation--source pair has a non-empty support status and disposition;
- every unique cited entry has field-level metadata, existence, and publication-status dispositions;
- every factual bibliography mismatch is linked to a finding or unresolved question; none is silently corrected or waived as formatting;
- every suspected fabricated/nonexistent entry has a documented integrity adjudication;
- every missing, partial, context-only, mismatch, or unverifiable row is linked to a finding, an explicit question, or a reasoned non-finding;
- no row remains `pending`, `unchecked`, or silently omitted;
- the citation-owning reviewer reports counts and limitations in the independent report.

After citation, claim, related-work, bibliography, status, dataset-source, or attribution edits, regenerate the complete ledger. Recheck every changed occurrence and every other occurrence that reuses the affected source. A previous 100 percent ledger does not carry over to a new frozen PDF or commit.
