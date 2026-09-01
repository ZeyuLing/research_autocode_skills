# Full-text citation and bibliography audit

Use this protocol in every initial review and independent re-review. For a doctoral thesis, R5 owns the bibliography-integrity half and R4 owns the citation-claim half; for a master's thesis, R3 owns both. The objective is to verify both the identity of every reference rendered in the PDF and every visible use of external evidence, not merely whether citation markers resolve.

## 1. Scope and evidence boundary

Audit all citation occurrences visible in the frozen PDF, including citations in abstracts, chapters, captions, tables, footnotes, appendices, and author/publication material when they make scholarly claims. Do not open source branches, comments, `.bib` files, auxiliary files, or citation commands; PDF visibility defines the corpus.

Treat one occurrence with multiple displayed references as multiple **citation--source pairs**. Repeated uses of the same source remain separate pairs because different sentences may make different claims. Audit every bibliography entry rendered in the PDF. Entries that exist only in a hidden `.bib` file are outside the submitted artifact and must not be opened or counted.

For every pair, bind the audit route to the cited work's complete rendered
identity. If the bibliography renders a DOI, `PublicIdentifier` must preserve
the full DOI token (prefer `https://doi.org/<complete DOI>`); a venue/series DOI
prefix such as `10.1109/cvpr52729` is not the cited paper's identifier. If no
DOI is rendered but an arXiv ID is present, preserve the complete arXiv work ID;
otherwise use an exact official URL rendered in the entry. `ContentSourceOpened`
must carry the same complete DOI/arXiv identity or an exact official URL also
rendered for that work. A failed or inaccessible attempt still records the
complete endpoint. A merely well-formed HTTP URL never proves source identity.

Before assigning any occurrence or pair ID, reconcile the mandatory Stage-P `00-citation-candidate-ledger.csv`. It contains every numeric square-bracket candidate extracted from non-bibliography PDF pages, including genuine references and lookalikes. Read every candidate in its exact rendered clause/table cell. A number that happens to fall inside the bibliography range is not enough: mathematical domains (`t \in [0,1]`, `K \in [3,8]`), numeric vectors/arrays or quantization levels (`[8,8,8,8,4]`), tensor/index notation, and other non-citation uses must remain classified `non-citation` with `MappedOccurrenceID=N/A`. Preserve them in the candidate ledger so completeness is auditable; never delete them to make the citation count appear closed. Every such row must use the exact `non-citation-role:<canonical-role>` token mechanically derived from the frozen-PDF context under the closed grammar in `ledger-validation.md`; free-form explanations, zeros, repeated integers, method/model names, or phrases such as “numeric specification” cannot suppress a candidate. Only `citation` rows map one-to-one to continuous occurrence IDs, and their expanded ordered numbers must match the source rows in `00-citation-inventory.csv`.

Stage P also preserves every unmatched square-bracket glyph in `00-unmatched-bracket-ledger.csv`, one row per glyph with its physical page, exact deterministic PDF-extraction context, and visible-role disposition. A positive count cannot be summarized as “none found.” The square endpoint of a deterministically recognizable half-open interval `[a,b)` or `(a,b]` uses exactly `visible-role:half-open-mathematical-interval`; an unrelated free-form role fails packet semantics. The bibliography span is derived independently from the unique longest rendered `[1]...[N]` entry run, inventory length, and same-page `References`/`参考文献` heading; ledger owners must invalidate the packet if an arbitrary body page is labeled as bibliography, if a candidate or glyph is omitted, or if an occurrence page/context does not match its mapped candidate.

The authoritative construction of raw page text, candidate/glyph ordering and windows, `ExpandedNumbers`, occurrence IDs, and Pair rows is the closed Stage-P extraction contract in `ledger-validation.md`; do not infer an alternative serialization, offset convention, or displayed-reference mapping from rendered appearance.

In an isolated blind-review round, follow `clean-room-orchestration.md` and start each ledger owner in a fresh context. Use only the frozen thesis PDF, its rendered bibliography, neutral PDF-derived inventories, governing rules, and public authoritative sources reachable from or identifiable through the rendered citations. Do not use conversation history, memory summaries, user explanations/rebuttals, earlier assistant issue tables, another actor's messages, the thesis source, `.bib`, Git history, private companion papers, internal repositories, logs, old rounds, source/provenance audits, or author declarations. Source-assisted provenance work is a separate non-review task and cannot alter the blind-review verdict.

## 2. Build two independently owned inventories

Create two files:

- `03-bibliography-audit-ledger.md`, owned by doctoral R5 or master's R3;
- `04-citation-claim-audit-ledger.md`, owned by doctoral R4 or master's R3.

Record in the relevant ledger:

- frozen PDF checksum, review date, and physical page count;
- number of visible citation occurrences;
- number of citation--source pairs after expanding clusters;
- number of unique displayed reference identities and rendered bibliography entries;
- unresolved citation markers, duplicate rendered entries, citation-to-reference mapping failures, and PDF extraction limitations.

Reconcile all machine-readable IDs against the neutral Stage-P inventories. Report duplicate, missing, and extra IDs explicitly; `pending=0` is not evidence that a row was never omitted. For a large thesis, process deterministic ID ranges in checkpointed batches, then concatenate and validate the masters before the owning reviewer signs them.

Also report the candidate-ledger closure totals: all numeric-bracket candidates, candidates classified as genuine citations, candidates classified as non-citations, and the reason classes for every exclusion. Those totals must reconcile exactly to the candidate ledger and citation inventory; a citation auditor may challenge Stage P's classification but must then invalidate/retry the packet rather than silently editing IDs inside R4/R3.

Use continuous deterministic rendered-reference IDs `REF0001...` in PDF order. In `03-bibliography-audit-ledger.md`, create a human-readable **bibliography master table** with exactly one row per bibliography entry rendered in the PDF:

| Reference ID | Displayed label | Cited? | Type | Title | Ordered authors | Year | Venue | Publication status | Volume/issue | Pages/article no. | Persistent IDs/URL/access date | Existence | Retraction/correction/superseding | Finding/disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

The bibliography table is a deterministic projection of the authoritative
long-form CSV, not free-form reviewer prose. Use the header above verbatim and
sort summary rows by `ReferenceID`. `Reference ID`, `Displayed label`, and
`Cited?` project their inventory/CSV scalars directly. Each audit column from
`Type` through `Retraction/correction/superseding` uses the fixed compact-JSON
field-record serialization defined in `ledger-validation.md`; grouped columns
use the documented fixed field order. `Finding/disposition` serializes all
seventeen field dispositions in that same order. Consequently, a title, author,
year, canonical value, verdict, evidence endpoint/date/note, or disposition
cannot differ between the signed Markdown and CSV while retaining the same
Reference ID.

The authoritative machine-readable master is `03-bibliography-audit-ledger.csv` in long form, with columns:

`ReferenceID,DisplayedLabel,Cited,Field,RenderedValue,CanonicalValue,Verdict,EvidenceEndpoint,EndpointType,CheckedAt,EvidenceNote,FindingDisposition,PDFSHA256`.

For every rendered entry, include exactly one row for each mandatory field: `type`, `title`, `ordered_authors`, `year`, `venue`, `publication_status`, `volume`, `issue`, `pages_or_article_number`, `doi`, `arxiv_id`, `arxiv_version`, `url`, `access_date`, `isbn_or_other_persistent_id`, `existence`, and `retraction_withdrawal_correction_superseding`. Each field verdict is `exact`, `mismatch`, `legitimate N/A`, or `unverifiable`; do not collapse fields into one check mark. Record both rendered and canonical values for every row, not only mismatches. Every row, including an `unverifiable` row, records the one complete `http(s)` authoritative endpoint actually attempted in `EvidenceEndpoint` and an ISO-8601 `CheckedAt`; “not opened,” a blank endpoint, or an unattempted source wishlist is not a completed audit. If the official route is inaccessible, keep its complete attempted endpoint, use `unverifiable`, and record the access result in `EvidenceNote`. When the rendered entry contains a DOI, arXiv ID, or official URL, the endpoint must preserve that complete work identity: a shortened DOI prefix is invalid even when it is a well-formed URL. `EvidenceEndpoint` is the primary authoritative route for that field verdict. Every additional redirect, failed official route, or fallback actually opened is recorded in `EvidenceNote` with the closed marker `accessed endpoint: <URL>`; the marker starts the field or follows a semicolon/newline, and the URL ends at a semicolon, newline, or field end. A bare URL in `EvidenceNote` is invalid because it cannot distinguish an accessed route from metadata text. Every `mismatch` row uses `FindingDisposition` as a closed single-ID reference: the whole cell is exactly one actual current owning-reviewer finding or question (`R5-Fxx`/`R5-Qxx` for a doctorate; `R3-Fxx`/`R3-Qxx` for a master's thesis), with no prefix, suffix, second ID, or free prose. `none`, `no finding`, `N/A`, `not applicable`, and equivalents are invalid alone or mixed with an owner ID. An `unverifiable` row instead follows the attempted-route contract and may remain a calibrated limitation unless the owner elevates it. Style-required capitalization, name abbreviation, or punctuation normalization is not a factual mismatch, but changed title content, omitted/reordered authors, wrong year, false venue/status, and wrong pages or article number are factual mismatches.

Each long-form row contains only the named field. Never paste the complete
rendered citation into `type`, `title`, `ordered_authors`, `venue`,
`publication_status`, `pages_or_article_number`, `access_date`, `existence`, or
correction/status rows. `title` is the title alone; `ordered_authors` is the
complete ordered author list alone; `year` is one four-digit year; venue and
publication/acceptance status are separate; pages or article number is not a
copy of the proceedings record; DOI and arXiv values are complete single work
identifiers; and `url`/`access_date` describe what the thesis bibliography
renders, not the auditor's endpoint/date. A `legitimate N/A` row uses an
explicit absent value in both value cells and is permitted only for metadata
that can genuinely be absent: volume, issue, pages/article number, persistent
identifiers, rendered URL, and access date. It cannot replace verification of
the required title, complete ordered authors, year, venue, publication status,
type, existence, or retraction/correction status. The accepted grammar includes
`N/A`, `none`, `not applicable`, `not rendered [in the bibliography]`,
`not available/provided/stated/assigned`, field-specific forms such as
`no issue assigned`, and their unambiguous Chinese equivalents such as
`不适用`, `未著录`, or `无卷号`. A field-specific marker must match its row:
`无卷号` is valid only for `volume`, `no issue assigned` only for `issue`, and
`无页码` only for `pages_or_article_number`; it never includes a complete citation string.
Reusing one entry-level string across unrelated fields is an invalid audit even
when every row has an endpoint and the row count is correct.

For `Verdict=exact`, rendered and canonical values must be field-equivalent.
This includes the complete ordered author sequence and separate venue and
publication-status fields, not only compact numeric/identifier scalars. Full
given names and their matching initials are compatible only when the ordered
author count, surnames, and surviving given-name tokens/initials agree; only
trailing middle-name tokens after a compatible first given name may be omitted,
but a leading given name cannot be skipped and changed or reordered authors are not
exact. This includes unambiguous uppercase surname-first forms such as
`DOE J, ROE R` and semicolon-delimited `Doe, J.; Roe, R.`. A common venue abbreviation may match its full name
only through a conservative explicit alias family (for example `CVPR` and the
IEEE/CVF Conference on Computer Vision and Pattern Recognition), including
organization-prefixed forms such as `IEEE CVPR`.
Established journal acronyms (`IEEE TPAMI`) and conservative dotted forms such
as `IEEE Trans. Pattern Anal. Mach. Intell.` may match the same full venue, but
unrelated or fabricated acronyms do not, and full-name token order is preserved.
Publication-status synonyms
are mapped only within a safe class (`published`, `final`, and `正式发表`);
`accepted`, `preprint`, `submitted`, `published`, `withdrawn`, and `retracted`
remain distinct; token boundaries prevent `unpublished` from matching
`published`. Page
ranges preserve their range delimiter during normalization (`12–34` may equal
`12-34`, but neither equals `1234`). A DOI scalar is exactly one DOI token,
optionally preceded by a DOI label, or one complete `doi.org` URL; prose that
merely contains a DOI is not a DOI field value.

Before accepting `legitimate N/A`, compare it with the frozen rendered entry.
If that entry visibly contains a DOI, arXiv identity, URL, labeled volume or
issue, labeled pages/article number, access date, or other persistent ID, the
N/A verdict is contradictory and invalid even though both value cells contain
an accepted absence marker. For `arxiv_version`, only an explicit `vN` suffix
means that a version is rendered; a versionless arXiv ID does not.
Unlabeled numeric volume/issue/pages clusters count only in bibliographic
context after an entry delimiter and at a terminal field boundary; title text
such as `12(3):45-67 ways ...` is not treated as publication metadata.

`EvidenceEndpoint` and `CheckedAt` document what the auditor used; they are not automatically fields that must be printed in the thesis bibliography. Whether the rendered reference itself must contain a URL or access date is controlled by the verified institutional template/citation style and the source type. When no binding rule requires a rendered URL or access date, an absent value is `legitimate N/A`, creates no finding, and does not affect the grade. A wrong printed URL that identifies a different object remains a factual identity mismatch. A repository's current archived/read-only state is a finding only when it contradicts a material availability/status claim made by the PDF; it is otherwise audit context.

Do not hand-copy any `03` or `04` deterministic Markdown row or any endpoint
receipt list. Complete the authoritative owned CSV first, run
`materialize_owner_outputs.py` with the current actor ID in the same fresh turn,
inspect the generated projection, and then run the owner's read-only gate. The
materializer escapes literal table delimiters, preserves every logical value,
and derives the duplicate-free endpoint list from the access fields above; it
does not decide whether a source exists, whether a field matches, or whether a
claim is supported.

In `04-citation-claim-audit-ledger.md`, create the following human-readable projection with one row per citation--source pair:

| Pair ID | Occurrence ID | PDF location | Exact attached proposition | Reference ID | Displayed label | Public source/identifier | Content source opened and exact locator | Support | Metadata/status | Severity/finding | Disposition/evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|

This table is an exact ordered projection of
`04-citation-claim-audit-ledger.csv`. Sort rows by `PairID`; project every scalar
field under the common escaping rule in `ledger-validation.md`; obtain
`Displayed label` from `00-bibliography-inventory.csv` by the row's
`ReferenceID`; for a dangling `REFnnnn` that has no bibliography row, project
the PDF-displayed numeric marker as `[n]`. Normalize CRLF/CR inside any CSV
field to LF and serialize each real LF into the two literal characters `\n`
in Markdown; collapsing or removing a line break is projection drift. The
combined source/locator cell is the compact JSON object
`{"content_source_opened":"<ContentSourceOpened>","exact_source_locator":"<ExactSourceLocator>"}`
with that exact key order and no extra whitespace. The CSV `PDFSHA256` is
projected through the checksum declaration and validated separately. An
unchanged Pair ID therefore cannot conceal drift in proposition, source,
locator, support, metadata status, severity/finding, or disposition/evidence.

Use continuous occurrence IDs `C0001...` in PDF reading order. For a citation cluster, repeat the occurrence ID for each displayed reference and assign continuous Pair IDs `C0001-S01`, `C0001-S02...C0001-S99`, followed by `C0001-S100` and wider ordinary decimal ordinals as needed through `S9999`. Sort Pair IDs by their numeric occurrence and source ordinals, never lexically. Pair ID is the primary key for reconciliation, chair joins, reclassification, and re-review. A displayed number missing from the rendered bibliography remains an auditable Pair row and must be reported as a paper defect. The exact proposition must state what the thesis asks that source to support; do not copy an entire paragraph when only one clause is attached.

For that dangling Pair row, use the closed serialization `Support=unverifiable`, `MetadataStatus=mismatch`, and `PublicIdentifier=no rendered bibliography entry`; leave `ContentSourceOpened` and `ExactSourceLocator` blank, and link `SeverityFinding` or `DispositionEvidence` to the owning reviewer's current `R4-Fxx/R4-Qxx` (doctorate) or `R3-Fxx/R3-Qxx` (master's) disposition. This sentinel records the absence visible in the frozen PDF; it is not a source identity. Any different support/status combination, a fabricated content endpoint, or an unlinked mismatch is invalid.

The authoritative CSV schema is exactly the contract in `ledger-validation.md`:

`PairID,OccurrenceID,PDFLocation,ExactAttachedProposition,ReferenceID,PublicIdentifier,ContentSourceOpened,ExactSourceLocator,Support,MetadataStatus,SeverityFinding,DispositionEvidence,PDFSHA256`.

The Markdown projection combines `ContentSourceOpened` and `ExactSourceLocator`
only through the fixed JSON serialization above; the CSV keeps them separate
and carries the source PDF checksum. `MetadataStatus` is exactly `verified`,
`mismatch`, or `unverifiable` and is reconciled by the chair against the
independent bibliography identity fields; it is not free-form prose.

Whenever `Support` is `partial`, `context-only`, `mismatch`, `unverifiable`, or
`not-needed`, or `MetadataStatus` is `mismatch`/`unverifiable`, the two
disposition columns must name an actual current owning-reviewer finding or
question (`R4-Fxx`/`R4-Qxx` for a doctorate; `R3-Fxx`/`R3-Qxx` for a master's
thesis). For `partial`, `context-only`, `unverifiable`, or `not-needed` only,
`DispositionEvidence` may instead begin with the machine-auditable marker
`reasoned non-finding:` followed by a substantive explanation. A support or
metadata `mismatch` is a contradiction and cannot use that waiver. A bare
`none`, `no finding`, or severity word is not a disposition.
The waiver marker belongs only in `DispositionEvidence`; placing it in
`SeverityFinding` does not satisfy the row. `SeverityFinding` contains `none`
or an owning current finding/question reference as applicable.
When a mismatch links a finding rather than a question, that finding is at least
`S3`; an `S4` label cannot waive a documented contradiction.

`ContentSourceOpened` is either blank under the documented unverifiable
contract or exactly one complete, parseable, source-specific HTTP(S) endpoint
whose content was used for the support verdict. It must carry the same complete
DOI/arXiv identity as `PublicIdentifier`/`RenderedEntry`, or exactly equal a
complete official URL exposed by either field. A host fragment, collection
route, empty `id=`, or path ending in a line-break fragment such as `conte` or
`_` is not a content endpoint. Any redirect, fallback, or failed route actually
opened must be retained in `DispositionEvidence` with the closed marker
`accessed endpoint: <URL>`; every URL occurrence must be independently marked,
even if the same URL also occurs elsewhere in that cell. Every marked auxiliary
must itself be a complete source-specific endpoint; it cannot repair a truncated
primary endpoint, while a legitimate child resource below a complete paper page
is not such a repair. URL fragments are ignored for canonical-page comparison
and cannot supply DOI/arXiv identity. A collection-shaped route with a nonempty
source query identity such as `article?id=...` is complete. The URL is followed
only by a semicolon, newline, or
field end. A complete auxiliary URL never repairs a truncated or identity-
unbound `ContentSourceOpened`. URLs appearing only in `PublicIdentifier`, the
attached proposition, an exact locator, or unmarked prose are identities/text,
not proof of access. Every source and marked auxiliary endpoint appears once in
both the owning ledger and reviewer receipts; a receipt-only or omitted recorded
endpoint fails closure.

For `direct`, `partial`, `context-only`, and `mismatch`, begin or delimit
`DispositionEvidence` with exactly one closed occurrence marker:

`occurrence binding: <PairID>@sha256=<SHA-256 of the NFKC/whitespace-normalized ExactAttachedProposition>`

The proposition itself must be the smallest exact text span recoverable from
that same Pair ID's Stage-P `AdjacentPDFText`; NFKC normalization, removal of a
soft hyphen, whitespace collapse, and a whitespace-free comparison accommodate
PDF extraction line breaks without allowing an adjacent row/window to be
substituted. If the disposition also labels an `occurrence-specific subject:`
or `attached proposition:`, that labeled text must equal
`ExactAttachedProposition` under the same normalization. The marker is a
binding, not evidence: retain a substantive source-content explanation after
it.

Locators and evidence remain source/occurrence-specific. Do not copy one
generic locator such as `Abstract; Section 3; Figure 2` or one generic support
sentence across many different sources or propositions. The gate removes URLs,
identifiers, numeric coordinates, the occurrence marker, and the exact attached
proposition before comparing templates, so changing only those interpolations
does not create distinct evidence. Repeated uses of the same work may share a
genuinely common locator; a large cross-source/cross-proposition template block
is aggregated across support classes. A concise locator such as `Abstract` alone
may legitimately recur and is not generic explanatory filler. For proposition
projection, remove only the exact numeric citation marker recovered for that
Stage-P occurrence; bracketed numeric data such as `[1,2]` remains substantive.
does not pass.

## 3. Static closure checks

Before semantic verification, check the complete rendered corpus:

1. every visible citation marker resolves to exactly one rendered bibliography entry;
2. there are no duplicate rendered-reference identities or unresolved citation markers;
3. every title matches the authoritative title in content, including subtitle when part of the official record;
4. the complete canonical author list and order are verified from the official record; when the governing rendered style legitimately abbreviates the display with `et al.`, record the canonical list in the ledger rather than treating style-compliant abbreviation as an omission;
5. the year follows the governing style's event/proceedings/issue rule and does not confuse online-first, preprint-upload, acceptance, conference, or issue year;
6. venue and status are verified separately: `published`, `accepted/in press`, `preprint`, `submitted/under review`, `withdrawn/retracted/corrected`, or `unverifiable`; an arXiv posting, project page, code repository, author CV, or search snippet does not by itself prove conference/journal acceptance;
7. journal volume/issue and page range or article number, and proceedings page range where assigned, match the official record; use `legitimate N/A` for arXiv-only and genuinely pageless records rather than inventing pages;
8. every persistent identifier or URL that is rendered or required by the binding style resolves to the same title and authors rather than merely returning a live page; a non-required missing URL is `legitimate N/A`, not a mismatch;
9. access dates are present and defensible only when the binding style requires them for that mutable resource; otherwise the rendered-field verdict is `legitimate N/A` even though the auditor still records `CheckedAt`;
10. retractions, withdrawals, expressions of concern, errata, and superseding versions are recorded when material;
11. datasets, software, standards, laws, websites, and repositories cite the appropriate primary artifact rather than an unrelated secondary paper;
12. self-citations and publications listed in the CV use accurate authorship and status.

Static closure is necessary but not sufficient. A visually resolved citation does not establish that a source supports the sentence citing it. Duplicate or unused keys that exist only in `.bib` are not part of a PDF-only review.

### Authoritative-source order for bibliography fields

Use the strongest available record and record the exact endpoint opened:

1. publisher/DOI landing page, official journal issue, or official conference proceedings paper page/PDF;
2. official conference accepted-paper list or program for an accepted but not yet published paper;
3. official preprint record such as arXiv for preprint identity and version only;
4. Crossref and DBLP as structured corroboration, not as substitutes when a first-party record is available;
5. institutional repository or author page only as secondary evidence.

Search-result snippets, generated citation sites, Semantic Scholar/OpenAlex-style aggregators, code README files, and another paper's bibliography are discovery aids, not final authority. If no first-party record is accessible, require two independent corroborating records where feasible and mark the field `unverifiable` rather than guessing. When no authoritative page exists or resolves, record the attempted official endpoint/search route, query/date, and negative result; do not invent an evidence URL merely to fill the field.

For `accepted/in press`, require an official accepted-paper list, publisher forthcoming record, DOI, or proceedings record that is publicly accessible. If no such public record is available, mark the status `unverifiable`; do not open a private acceptance document or upgrade `submitted`, `under review`, or `arXiv preprint` from author assertion alone.

### Fabricated or nonexistent citation escalation

Open an integrity investigation when any of the following occurs:

- the DOI or persistent identifier resolves to a different title or author set;
- the claimed proceedings volume/page range belongs to another paper;
- the official journal issue, proceedings, or accepted-paper list affirmatively contradicts the claimed venue/status;
- the entry combines a title, author list, venue, year, or pages from different works;
- exact-title, author-title, identifier, and official venue searches all fail and an authoritative record indicates the claimed work does not exist.

Do not label a paywalled, obscure, future, private, or temporarily inaccessible work fabricated solely because it was not found quickly. Record search routes and negative evidence. Once the chair substantiates a fabricated/nonexistent citation as an `integrity/foundational S0`, the skill-default conclusion is **D — 不同意答辩**. A source that is merely inaccessible, uncertain, or affected by a plausible local metadata typo is not yet that `S0`; retain it as an evidence-calibrated question or lower-severity finding.

## 4. Verify every citation occurrence semantically

For every citation--source pair:

1. copy the smallest exact proposition attached to the citation from that
   Pair ID's frozen `AdjacentPDFText`, rather than paraphrasing it or borrowing
   a neighboring table/paragraph window;
2. open the cited primary source content in the version that matches the bibliography and frozen review date, and record the exact public `http(s)` content endpoint; a publisher metadata page, DOI record, accepted-paper list, or proceedings index verifies identity/status only, not substantive content;
3. verify the proposition against the source's actual task, assumptions, method, data, protocol, result, and conclusion, and record a source page, section, theorem, table, figure, equation, record field, or equivalent exact locator;
4. distinguish what the source directly states from the thesis author's inference;
5. check that a survey or secondary source is not being used to launder a stronger claim than its primary evidence supports;
6. for clusters, determine what each source contributes; do not allow one relevant paper to mask unrelated padding;
7. for comparisons or priority claims such as “first,” “most,” “state of the art,” “widely used,” or “few studies,” verify the search/date boundary or require narrower wording;
8. for quotations, definitions, numerical values, dataset statistics, policy rules, and attributed limitations, verify exactness and context;
9. for inaccessible source content, record the attempted persistent identifier or official endpoint and classify substantive support as `unverifiable`, never `direct`/`partial`/`context-only` from metadata alone. The exception is when the attached proposition is itself only publication metadata, in which case the official metadata record is content-appropriate evidence.

For `unverifiable`, distinguish an identifier from opened source content.
`ContentSourceOpened` names content that was actually opened; “source-content
access attempt” is not an exact locator. Record a concrete source-specific
failure or insufficiency result (for example HTTP status, timeout, connection
reset, access denial/paywall, or an identified abstract that does not expose
the needed proposition). Do not reuse one blanket “unavailable in this review
environment” waiver across unrelated references. Repeated citations to the
same inaccessible work may share the same source-specific disposition, but a
whole bibliography cannot be converted into schema-valid `unverifiable` rows
by changing only the URL, identifier, or quoted/unquoted work title. The
dominance check targets a clear majority pattern rather than a minority of
independently documented sources that happen to share one HTTP failure class.

Assign one support status:

- `direct` — the source directly supports the attached proposition in the stated context;
- `partial` — only part of the proposition or a narrower version is supported;
- `context-only` — relevant background, but not evidence for the attached factual or comparative claim;
- `mismatch` — the source contradicts or does not support the proposition;
- `unverifiable` — the source could not be accessed or identified sufficiently;
- `not-needed` — the citation is attached to author reasoning that does not require external attribution; retain only with an explicit reason.

Do not infer support from title similarity, abstract keywords, citation count, venue reputation, or another paper's reference list. Avoid excessive quotation; record a concise paraphrase and a precise page, section, theorem, table, or official metadata endpoint where possible.

## 5. Finding calibration

Apply the ordinary six-question finding test and minimum sufficient remedy.

- `S0` (`integrity/foundational`): fabricated/nonexistent source, systematic deceptive attribution, or citation conduct that creates a substantiated integrity blocker.
- `S1`: an unsupported or misrepresented source is indispensable to a central novelty, correctness, dataset, safety, or thesis-level conclusion.
- `S2`: a material related-work, method, data, protocol, or result claim is only partially supported or omits a decisive source, but can be repaired without overturning the thesis.
- `S3`: local missing citation, ambiguous placement, metadata/status error, irrelevant cluster member, or formatting inconsistency.
- `S4`: optional source enrichment that is not necessary for correctness or fair positioning.

Prefer repairing the sentence, moving the citation, splitting a compound claim, adding the correct primary source, or correcting metadata. Do not demand new experiments merely because a citation is weak.

### Reviewer independence

For a doctoral panel, R4 and R5 receive the same frozen PDF and may receive a mechanically generated inventory extracted only from that PDF, but they must not edit a shared ledger, exchange provisional findings, or read each other's ledger/report before freezing their own verdicts. **Within the two exhaustive audit deliverables**, R5 signs the source-identity and field-accuracy dispositions, while R4 signs whether each source supports the attached proposition. This is ledger workload allocation only: both remain comprehensive whole-thesis reviewers, and either records any problem found in any gate. The chair reconciles duplicate or dependent findings only after both reports are frozen.

Each ledger records the owner's fresh-context and input-receipt/access declarations, including prompt hash, all received blocks, exact local artifacts opened, and every public endpoint used. The owner receives exact paths and must not enumerate neighboring rounds or discover prior artifacts from the workspace.

### Mandatory chair cross-ledger consistency gate

After both independent ledgers are frozen, join them by stable rendered reference identity/displayed label and check every cited reference before synthesis:

1. the source identity recorded by R4 must agree with R5's authoritative title, ordered authors, persistent identifier, and existence verdict;
2. if R5 marks the cited work's identifier, title/author combination, or existence as `mismatch`, every R4 occurrence using that record is invalid until the intended source is identified; it cannot remain `direct`, `partial`, or `context-only` merely because the row has a non-empty disposition;
3. if R4's own metadata note names a work different from the thesis bibliography or attached proposition, classify the pair as `mismatch` (or `unverifiable` only when identity truly cannot be resolved), regardless of R4's provisional support label;
4. if R4 and R5 used different versions or records, state which one governs and why; do not silently merge their metadata;
5. reconcile the set of cited rendered references and the occurrence count, and list every cross-ledger conflict in the chair report.

A **substantive** conflict changes source identity, existence, publication status material to the proposition, or whether the source supports the proposition. It fails the combined citation gate and must be recorded as at least `S2`; a central or integrity consequence may raise it to `S1` or `S0`. Preserve both independent reports, but do not issue **A — 同意答辩** until the thesis is corrected and the affected bibliography entries, every occurrence reusing them, and both ledgers are re-audited in a new frozen round. Use B, C, or D according to the adjudicated severity. A punctuation, capitalization, abbreviation, house-style difference, or omission of a URL/access date that the binding style does not require leaves identity and support unchanged and is not a substantive conflict; a verified style-required local field omission is at most `S3/W` unless it actually changes source identity. Mechanical completeness (`pending=0`, expected row count, or a live URL) never overrides the identity check.

## 6. Completion and re-review gate

The bibliography-integrity gate passes only when:

- the bibliography Markdown master table has exactly one summary row per rendered entry and the CSV has exactly the mandatory long-form field rows per entry;
- every mandatory bibliography field has an `exact`, `mismatch`, `legitimate N/A`, or `unverifiable` verdict plus the complete authoritative endpoint actually attempted; an `unverifiable` row additionally records the route/query/date and negative result;
- every unique cited rendered entry has field-level metadata, existence, and publication-status dispositions;
- every factual bibliography mismatch is linked to a finding or unresolved question; none is silently corrected or waived as formatting;
- every suspected fabricated/nonexistent entry has a documented integrity adjudication;
- no row remains `pending`, `unchecked`, or silently omitted;
- the inventory/CSV/Markdown reference-ID sets reconcile exactly, with zero duplicate, missing, or extra IDs;
- the bibliography-owning reviewer reports counts and limitations in the independent report.

The citation-claim gate passes only when:

- ledger occurrence counts reconcile with the frozen PDF inventory;
- every citation--source pair has a non-empty support status and disposition;
- every missing, partial, context-only, mismatch, or unverifiable row is linked to a finding, an explicit question, or a reasoned non-finding;
- no row remains `pending`, `unchecked`, or silently omitted;
- the inventory/CSV/Markdown Pair-ID sets reconcile exactly, with zero duplicate, missing, or extra IDs;
- the citation-claim-owning reviewer reports counts and limitations in the independent report.

The combined citation gate passes only when the chair's reference-wise cross-ledger join has no unresolved identity/support contradiction. Record the joined-reference count and conflict count in the chair synthesis or re-review report.

After citation, claim, related-work, bibliography, status, dataset-source, or attribution edits, freeze the new PDF and regenerate the affected ledger or both ledgers from that PDF. Recheck every changed entry or occurrence and every other occurrence that reuses the affected source. Previous 100 percent ledgers do not carry over to a new frozen PDF.
