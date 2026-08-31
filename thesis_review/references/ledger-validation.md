# Machine-readable ledger and bundle validation

Use these contracts for every complete review round. Markdown reports contain reasoning and signed dispositions; CSV files are the authoritative row sets for completeness, deterministic IDs, and reconciliation. Mechanical validation never replaces reviewer judgment.

## 1. CSV conventions

- UTF-8 with a header row and RFC-4180-style quoting for commas, quotes, or newlines.
- Stable, case-sensitive IDs assigned in frozen-PDF reading order: pages are
  `P0001...`; rendered bibliography entries are `REF0001...`; citation
  occurrences are `C0001...`; and sources within an occurrence are
  `C0001-S01...C0001-S9999`. Source ordinals use at least two digits (`S01`
  through `S99`) and ordinary wider decimal rendering from `S100` onward.
  Each sequence is continuous with no gaps.
- Never reuse an ID for a different rendered object or citation pair.
- `pending`, `unchecked`, placeholder ellipses, and silently blank mandatory verdicts fail completion.
- In final `02-page-layout-ledger.csv`, every cell is nonempty and nonplaceholder except `PrintedPage`, which may be blank only when no printed label is rendered. In `03-bibliography-audit-ledger.csv`, every cell is nonempty and nonplaceholder: even an `unverifiable` bibliography row retains the complete authoritative `EvidenceEndpoint` actually attempted and explains the access failure in `EvidenceNote`. Whitespace-only cells are blank; use an explicit contract value such as `N/A` only where that field's closed vocabulary permits it.
- Process large ledgers in deterministic ID ranges and checkpoint batches; concatenate only after duplicate/missing/extra validation.
- Every sidecar records the frozen PDF SHA-256 in its companion Markdown report and, when practical, in a `PDFSHA256` column.

For every authoritative-CSV-to-Markdown projection below, a scalar cell uses
the exact CSV string after CRLF/CR normalization to LF and JSON string escaping
with Unicode retained, but with the surrounding JSON quotes omitted. Thus
ordinary values remain ordinary text, a real newline becomes `\n`, and a
literal backslash remains distinguishable from that newline escape. After this
serialization, encode each literal Markdown table delimiter with the production
materializer. An ordinary literal pipe is written as `\|`; when the logical
cell has `k` consecutive backslashes immediately before that pipe, the source
uses `2k+1` backslashes so parsing preserves both the backslashes and the pipe.
The validator decodes only this table-source escape before comparing.
Markdown table padding is not data, so authoritative CSV values that depend on
leading or trailing whitespace cannot reconcile. Headers are case-sensitive and
must use the documented spelling and order. Rows use deterministic ID order,
and every projected non-hash cell is compared, not only the ID. `PDFSHA256` is
bound by the Markdown checksum declaration and validated on every authoritative
CSV row rather than duplicated as a table column.

Ledger owners do not hand-build these deterministic pipe tables. After every
owned-CSV change and before the read-only owner gate, doctoral R4/R5 or master's
R3 runs `python rules/scripts/materialize_owner_outputs.py <exact-round-root> <actor-id>`
in the same fresh actor turn. Exit `0` and first nonempty stdout
`MATERIALIZED` mean only that the owned Markdown projections and duplicate-free
endpoint receipt lists were rebuilt; the command does not validate or change a
semantic CSV value. The actor inspects the result and then runs its scoped gate
to `PASS`. The materializer is a staged rule input, never thesis evidence, and
Stage O must not run it after the owner freezes. It may deduplicate an endpoint
already present in the authoritative access fields, but it fails rather than
silently erasing a receipt-only URL: the actor must first record a route it
actually opened with the closed marker, or remove a false declaration.

## 2. Required machine-readable contracts

### Stage-P inventories

- `00-page-inventory.csv`: `PageID,PhysicalPage,PrintedPage,Region,MechanicalSignals,PDFSHA256`
- `00-bibliography-inventory.csv`: `ReferenceID,DisplayedLabel,RenderedEntry,Cited,PDFSHA256`
- `00-citation-candidate-ledger.csv`: `CandidateID,PhysicalPage,Marker,ExpandedNumbers,Classification,ClassificationEvidence,MappedOccurrenceID,AdjacentPDFText,PDFSHA256`
- `00-unmatched-bracket-ledger.csv`: `GlyphID,PhysicalPage,Glyph,AdjacentPDFText,Disposition,PDFSHA256`
- `00-citation-inventory.csv`: `PairID,OccurrenceID,PDFLocation,DisplayedReferenceID,AdjacentPDFText,PDFSHA256`

`Region` is a PDF-derived structural field, not free prose.  The shared Stage-P/full validator derives numbered chapter boundaries from strong rendered page-top cues: an independent Chinese/English chapter heading, a cross-line `CHAPTER 4` plus independent title, or a bare `4 Title` line duplicated by the running header or followed by the chapter's `4.1` heading.  Dot-leader or unanchored table-of-contents/list entries and prose such as “Chapter 4 presents...”/“第4章介绍了...” or an ordinary `4.1` reference are not boundaries.  It separately derives the unique rendered bibliography run described below and independent appendix/back-matter headings such as `附录`/`Appendix`, `致谢`/`Acknowledgements`, and `作者简历`/`Curriculum Vitae`.  Every page row must agree with those boundaries.  Descriptive labels may refine a canonical class (`front matter — Chinese abstract`, `chapter — methods`, or `body — results`, for example).  `separator`/`boundary`/`blank` is accepted only when the rendered page is substantively empty after repeated page furniture and a standalone page number are removed; it cannot hide a nonempty chapter boundary.  A numbered label such as `chapter 3` or `第3章` is a stronger claim and must equal the PDF-derived chapter number; it cannot cover the first page of rendered chapter 4.

The validator independently derives the bibliography's contiguous physical-page span from the unique **longest** rendered line-start entry run `[1]...[N]`, requires its length to equal the bibliography inventory, and requires a rendered `References`/`参考文献` heading on the run's first page; a free-text `Region` value or an isolated body `[1]` cannot remove an arbitrary body page from extraction. `RenderedEntry` is mechanically bound row by row: for `[n]`, take the raw extracted text after that line-start label through the raw start of `[n+1]`; when the boundary crosses pages, join the current-page suffix, every intervening page, and the next-page prefix with LF; for `[N]`, continue through the end of the last bibliography page. Apply only `re.sub(r"\s+", " ", value).strip()` to that slice. The resulting string—not an independently retyped citation—must equal `RenderedEntry` byte for byte. An exact duplicate between two correctly extracted rows remains in the packet as a possible thesis defect for the bibliography reviewer; packet validation must not erase or reject it merely for being duplicated.

The validator then re-extracts every balanced square-bracket span containing at least one digit from every non-bibliography physical page of the frozen PDF with the bundled `pypdf` text extractor; spans may cross extracted line breaks and have no silent length cutoff. Stage P and every later PDF-reading or PDF-derived-packet scoped/full gate use the same bundled workspace Python for the round; Stage S is a PDF-free deterministic projection and does not import the extractor. Stage P records `PDF extraction runtime: pypdf=<pypdf.__version__>` in the canonical manifest identity block, and every validator compares it exactly with its own runtime before accepting the packet. Do not launch an actor with an unpinned `uv --with pypdf` or another ad-hoc interpreter: a `pypdf` version change can alter extracted line breaks, raw offsets, bibliography slices, and adjacent windows even when the PDF bytes are identical. A future bundled-runtime upgrade is valid only for a newly generated packet whose complete round uses that one version. Page text is exactly the raw string returned by `PdfReader(path, strict=False).pages[i].extract_text() or ""`, with physical pages numbered from one. Candidate matching, bracket pairing, ordering, and window offsets operate on that unnormalized string. Only after a raw window is sliced are whitespace runs replaced by one ASCII space and the ends stripped; no Unicode normalization is applied.

Candidates are every nonempty nonnested `\[[^\[\]]+\]` span containing a decimal digit, ordered by physical page and raw start offset outside the derived bibliography span. Marker normalization removes whitespace, maps `，` to `,`, and maps `–`/`—` to `-`; the ledger's `Marker` cell must itself equal that canonical normalized marker, rather than relying on the validator to normalize a different stored spelling. Candidate context is the complete span plus up to 160 raw characters on each side. The stored `AdjacentPDFText` must equal the one deterministic normalized window byte for byte; a second normalization during comparison is forbidden because it could conceal ledger drift. `ExpandedNumbers` is the exact no-space ASCII-semicolon-separated serialization of the inclusive ordered expansion of one-to-four-digit integers/ranges, including descending ranges and duplicates and with ordinary integer rendering; all decimal/mixed/formula spans use exactly `N/A`. The candidate ledger contains exactly that sequence with continuous `BC0001...` IDs and the frozen-PDF hash. `Classification` is exactly `citation` or `non-citation`.

For every `non-citation` row, `ClassificationEvidence` is not prose. It must byte-for-byte equal the validator-derived token `non-citation-role:<canonical-role>`, where the closed roles are `non-integer-expression`, `math-domain`, `index-expression`, `coordinate`, `parameter-list`, `declared-numeric-collection`, `enumeration-run`, and `code-data-literal`. The validator derives the one role directly from the re-extracted frozen-PDF prefix, marker, and suffix; the actor cannot select a role by assertion. The predicates require strong local syntax: a non-pure-integer span with an actual decimal, operator, delimiter, function, or mathematical-symbol signal (not merely a malformed marker such as `[1a]`); membership, distribution-support, or explicitly bound domain syntax; an expression-continuing array index; an explicitly introduced integer coordinate; an explicitly named parameter-value list; an explicitly bound vector/array/shape/quantization-level collection; a headed bracket-number option run; or an assignment/return data literal. A bare positive-integer marker, a free-form claim such as “model/data numeric specification,” an identifier immediately followed by a bracketed number, a zero, or a repeated number is not sufficient. Thus `ACTOR[11]`, `MotionGPT[8]`, `运动图[9]`, `[4-5]`, or `[1-3,26,30]` remain citations unless their actual PDF syntax independently satisfies a closed role, while `x[1] = ...`, `t \in [0,1]`, `t\sim U[0,1]`, `top-k values [1,5,10]`, and an explicitly introduced quantization vector may be non-citations. An uncommon legitimate role outside this grammar is a Stage-P validation failure requiring a clean retry after the shared grammar and regression tests are extended; it cannot be resolved by free-form evidence or by silently deleting the candidate.

Every unmatched `[` or `]` on a non-bibliography page is derived by one left-to-right LIFO page-level pairing scan. Remaining opening glyphs and unmatched closing glyphs are merged in page/raw-offset order and receive continuous `UBG0001...` rows. Each context is the raw slice `text[max(0, offset-160):min(len(text), offset+161)]` before the same whitespace normalization. The physical page, glyph, and normalized context must equal the validator extraction; the disposition explains the visible role and cannot claim that none were found. A positive manifest count equals this row count and names the sidecar; only a zero count permits an explicit none-found disposition. Any candidate or unmatched-glyph omission, extra row, reordering, page/marker/context mismatch, classification/mapping mismatch, or obvious mathematical false positive invalidates Stage P.

The Stage-P citation inventory is mechanical after candidate disambiguation. Citation-classified candidates alone receive continuous `Cnnnn` occurrence IDs; a non-citation candidate consumes no occurrence ID. Expanded element `n` at one-based source ordinal `k` creates exactly one Pair row whose ID is `Cnnnn-S{k:02d}` (`S01`--`S99`, then `S100` and wider ordinary decimal rendering through `S9999`) and whose `DisplayedReferenceID` is `REF{n:04d}`. Pair rows preserve the expanded-vector order; every occurrence maps to exactly one candidate and every candidate occurrence maps back. `PDFLocation` names the candidate's valid physical page, and `AdjacentPDFText` copies the candidate's deterministic normalized extraction window exactly; it is an anchor, not a semantic proposition verdict. If a displayed citation number has no rendered bibliography row, retain that Pair row unchanged: the dangling citation is a paper defect for reviewer audit, not a reason for the neutral packet builder to delete the evidence or fail its own extraction gate.

### Page audit

- `02-page-layout-ledger.csv`: `PageID,PhysicalPage,PrintedPage,Region,DominantContent,Signals,InspectionModeScale,RenderDPI,RenderArtifactIDHash,NeighborPagesChecked,Disposition,Evidence,PDFSHA256`

The Page-ID set must exactly equal `00-page-inventory.csv`; `PhysicalPage` must form `1..N` with no gaps or duplicates; and `Pnnnn` must map to physical page `nnnn` in both inventories. Every suspect page uses `full-scale`; every page has a non-empty disposition and inspection mode. A final `Disposition` is exactly `clean`, `intentional`, or `finding Rn-Fxx` for the assigned page owner; `recheck after edit`, `pending`, `unchecked`, `open`, and `unresolved` are invalid final states. Every finding reference resolves to an actual current owner finding. The owner report's actionable layout count is the number of distinct referenced finding IDs, so repeated page rows for one finding count once. `RenderDPI` normally follows the 160--200 dpi audit target; the validator accepts 120--600 only as a mechanical sanity range. Retain one decodable PNG as `page-renders/<PageID>.png`; its dimensions must match the frozen PDF page at the declared DPI, and `RenderArtifactIDHash` is that file's exact 64-hex SHA-256, optionally prefixed by the matching PageID. The `02` Markdown table uses exactly the twelve headers in `rendered-pagination-audit.md`, sorts by `PageID`, and projects `PageID,PhysicalPage,PrintedPage,Region,DominantContent,Signals,InspectionModeScale,RenderDPI,RenderArtifactIDHash,NeighborPagesChecked,Disposition,Evidence` field by field. Each Markdown master must contain exactly one complete pipe table with its documented ID header, an immediately following separator row, consistent column counts, and every corresponding CSV ID exactly once in that table's ID column. The ID column remains the unique primary-key projection. The matching current row's PageID may recur as the prefix of its own `Render artifact ID/hash`; existing current-round PageIDs may also occur as explicit cross-references in `Neighbor pages checked` and `Evidence`. Every such cross-reference must belong to the current Page-ID set. Page IDs remain forbidden in every other column, prose, code fence, or unrelated table, and an unknown `Pnnnn` is invalid even in a permitted cross-reference column. Prose mentions and standalone pipe rows do not count as ledger rows and invalidate the projection.

Every ledger row preserves that page's Stage-P `MechanicalSignals` in
`Signals` or `Evidence`. On a thesis-length ledger, page evidence must vary with
the rendered content, `DominantContent` may not merely duplicate `Region` on a
majority of pages, and one generic signal/evidence sentence may not be copied
through the whole document. An `intentional` row contains a structural
rationale for the blank/separator/template page. These are semantic
completeness conditions, not substitutes for the retained PNG checks.

### Bibliography audit

- `03-bibliography-audit-ledger.csv`: `ReferenceID,DisplayedLabel,Cited,Field,RenderedValue,CanonicalValue,Verdict,EvidenceEndpoint,EndpointType,CheckedAt,EvidenceNote,FindingDisposition,PDFSHA256`

For each `ReferenceID`, the `(ReferenceID,Field)` key is unique and the mandatory field set is exactly:

`type,title,ordered_authors,year,venue,publication_status,volume,issue,pages_or_article_number,doi,arxiv_id,arxiv_version,url,access_date,isbn_or_other_persistent_id,existence,retraction_withdrawal_correction_superseding`.

`Verdict` is one of `exact`, `mismatch`, `legitimate N/A`, or `unverifiable`. Every row, including `unverifiable`, records one complete `http(s)` authoritative endpoint actually attempted. `CheckedAt` is an ISO-8601 date or datetime. For `unverifiable`, `EvidenceNote` records the access failure or authoritative-record insufficiency at that endpoint; a blank endpoint is not a completed bibliography audit. Any redirect, failed secondary route, or fallback actually opened in addition to `EvidenceEndpoint` is retained inside `EvidenceNote` with the closed marker `accessed endpoint: <URL>`; the marker begins the field or follows a semicolon/newline, and the URL ends at a semicolon, newline, or field end. Every HTTP(S) URL in `EvidenceNote` must use that marker. The authoritative bibliography access set is the duplicate-free union of all nonblank `EvidenceEndpoint` values and all valid marked endpoints, in first-observed CSV order. For `mismatch`, the entire `FindingDisposition` cell is exactly one current owning-reviewer `Rn-Fxx` or `Rn-Qxx` ID—no prefix, suffix, free prose, second ID, `none`, `N/A`, or mixture with any exemption phrase. Canonical `REFnnnn` tokens occur only in the `ReferenceID` column/cell; they never recur in another CSV field, prose, code fence, or unrelated Markdown column.

`RenderedValue` and `CanonicalValue` are field-specific scalars. Repeating a
complete rendered entry across three or more unrelated fields, or placing an
entry-level DOI/URL/type/venue delimiter inside a title, ordered-author, or
venue scalar, is invalid. `year`, DOI, arXiv ID/version, URL, and access date
must satisfy their field shapes. `legitimate N/A` is restricted to fields that
can genuinely be absent (`volume`, `issue`, pages/article number, persistent
identifiers, rendered URL, and access date); it cannot replace required title,
complete ordered authorship, year, venue, publication status, type, existence,
or retraction/correction-status checks. It requires explicit absent values in
both value cells, using the documented English/Chinese absent-value
grammar; a field-specific marker must match its named row, a citation-shaped
value is never an absence marker, and an absent
field marked `exact` is invalid. When an explicit `DOI:`/`DOI ` or `arXiv:`
field and a PDF-line-broken URL disagree only because the URL lost a trailing
character, the complete explicit field binds the work identity and the
truncated route does not pass.

For exact comparisons, full given names may match their initials, or omit only
trailing middle-name tokens after a compatible first given name, under an unchanged ordered author count with
matching surnames and surviving given tokens/initials. Common
venue acronyms may match their full expansion only through the maintained
explicit alias family; organization prefixes, established journal acronyms,
and conservative ordered dotted token abbreviations are supported. Unordered
token sets and fabricated acronyms are not equivalence evidence. Publication-status
synonyms are restricted to one semantic class; accepted, preprint, submitted,
published, withdrawn, and retracted are not interchangeable, and unpublished
is not published. An
optional-field `legitimate N/A` also fails when the frozen `RenderedEntry`
visibly exposes that DOI/arXiv/URL/volume/issue/pages or other named field.
An arXiv-version field is exposed only by an explicit `vN` suffix.

The `03` Markdown projection sorts by `ReferenceID` and uses the exact fifteen
headers in `citation-audit.md`. Its first three cells project `ReferenceID`,
`DisplayedLabel`, and `Cited`. Every remaining audit-field record serializes as
compact JSON with this exact key order and no insignificant whitespace:

`{"field":"<Field>","rendered":"<RenderedValue>","canonical":"<CanonicalValue>","verdict":"<Verdict>","evidence_endpoint":"<EvidenceEndpoint>","endpoint_type":"<EndpointType>","checked_at":"<CheckedAt>","evidence_note":"<EvidenceNote>"}`

Single-field columns contain that object. Grouped columns contain a compact JSON
array in this fixed order: `Volume/issue = [volume,issue]`;
`Persistent IDs/URL/access date =
[doi,arxiv_id,arxiv_version,url,access_date,isbn_or_other_persistent_id]`.
The other columns map one-to-one to `type`, `title`, `ordered_authors`, `year`,
`venue`, `publication_status`, `pages_or_article_number`, `existence`, and
`retraction_withdrawal_correction_superseding`. `Finding/disposition` is a
compact JSON array of
`{"field":"<Field>","finding_disposition":"<FindingDisposition>"}` objects
in the complete seventeen-field order printed above. Every CSV ReferenceID must
therefore occur exactly once, and every long-form field value has one
deterministic signed Markdown projection.

### Citation-claim audit

- `04-citation-claim-audit-ledger.csv`: `PairID,OccurrenceID,PDFLocation,ExactAttachedProposition,ReferenceID,PublicIdentifier,ContentSourceOpened,ExactSourceLocator,Support,MetadataStatus,SeverityFinding,DispositionEvidence,PDFSHA256`

The Pair-ID set and row order must exactly equal `00-citation-inventory.csv`; ordering is numeric by occurrence/source ordinal, so `S99` precedes `S100`. `Support` is one of `direct`, `partial`, `context-only`, `mismatch`, `unverifiable`, or `not-needed`, and `MetadataStatus` is one of `verified`, `mismatch`, or `unverifiable`. A substantive support verdict other than `unverifiable` requires one complete, parseable, source-specific `http(s)` endpoint in `ContentSourceOpened` and a structured locator such as `page 14`, `section 3.2`, `Table 2`, `Figure 4`, `Equation 7`, `Abstract`, or `publisher record: DOI ...`; a bare word such as `section` is invalid. The content endpoint must carry the complete DOI/arXiv identity in `PublicIdentifier`/`RenderedEntry` or exactly equal a complete official URL exposed by either field. Host fragments, empty-ID routes, collection pages, and paths ending in `_` or a known line-break fragment fail; a complete auxiliary `accessed endpoint:` URL never repairs the primary field. Publication metadata alone is acceptable only when the attached proposition is publication metadata. A `ReferenceID` absent from the rendered bibliography uses exactly `Support=unverifiable`, `MetadataStatus=mismatch`, `PublicIdentifier=no rendered bibliography entry`, blank `ContentSourceOpened`/`ExactSourceLocator`, and a current owning-reviewer finding/question link. The Markdown projection uses the exact twelve headers in `citation-audit.md`, sorts by numeric Pair-ID ordinals, and compares every projected field. `Displayed label` is the exact `00-bibliography-inventory.csv` label for an existing row; for a dangling `REFnnnn`, it is `[n]` derived from the frozen PDF marker. `Content source opened and exact locator` is compact JSON with exact key order `{"content_source_opened":"<ContentSourceOpened>","exact_source_locator":"<ExactSourceLocator>"}`; all other non-hash CSV fields map one-to-one to their named Markdown column. Every CSV PairID must occur exactly once as a complete table cell, except that the same row's PairID occurs once more inside its required occurrence-binding marker in `Disposition/evidence`.

For `direct`, `partial`, `context-only`, and `mismatch`,
`DispositionEvidence` contains exactly one closed marker
`occurrence binding: <PairID>@sha256=<64-hex>`, where the digest is SHA-256 of
`ExactAttachedProposition` after NFKC normalization, soft-hyphen removal,
whitespace collapse, and trimming. `ExactAttachedProposition` must itself be a
normalized exact substring of the same Pair ID's `AdjacentPDFText`; the
validator also permits the whitespace-free form to accommodate extraction
spaces/line breaks. Any explicit `occurrence-specific subject:` or `attached
proposition:` label in the disposition must normalize to that exact proposition.
The marker cannot stand alone: substantive evidence remains mandatory.

For those four support classes, identity-stripped `ExactSourceLocator` and
`DispositionEvidence` signatures are checked separately. The signature removes
URLs, DOI/arXiv/work/row IDs, numeric coordinates, binding markers, labeled
subjects, and the row's complete attached proposition. A signature repeated
across at least 12 distinct `(ReferenceID, proposition)` units fails when it
spans at least six distinct references or eight distinct propositions. The
diagnostic reports the support class, distinct-reference count, unit count, and
threshold. Repeated occurrences of one work below that cross-source/
cross-proposition boundary remain available for reviewer judgment.

An `unverifiable` row records a concrete source-specific failure or
content-insufficiency result. “Source-content access attempt” is not a locator,
and changing only the endpoint under one blanket environment-level waiver is
not a completed semantic audit. The validator permits repetition for multiple
occurrences of the same work but rejects a dominant identical waiver reused
across many distinct references.

The owning audit artifact and owning review report must list in their `public_endpoints=[...]` receipt every authoritative endpoint that their bibliography or citation master says was opened, including every valid marked auxiliary route. Each exact endpoint occurs once in the receipt. Declaring `[none]` while `EvidenceEndpoint`, `ContentSourceOpened`, or a valid `accessed endpoint:` marker contains a source is an invalid access record. A receipt-only endpoint is equally invalid. An `unverifiable` bibliography row still retains its complete attempted authoritative endpoint and contributes it to the receipt; it never invents a route or leaves `EvidenceEndpoint` blank.

### Chair and summary reconciliation

- `91-revision-ledger.csv`: `LedgerID,Priority,ChairFindingID,SourceReviewerFindingIDs,Severity,S0Subtype,Remedy,ExactPDFAnchor,DirectObservation,EvidenceStatus,MinimumEditEvidence,Dependency,Owner,Status,Verification`
- `91-ai-actionable-ledger.csv`: `AIFindingID,Impact,ExactPDFAnchor,DirectStyleObservation,MinimumEditingAction,Status,Verification`
- `92-new-evidence-or-experiments.csv`: `EvidenceItemID,LedgerID,ChairFindingID,Remedy,Item,ClaimThatDependsOnIt,WhyWritingIsInsufficient,MinimumViableEvidence,ConsequenceIfUnavailable`
- `93-current-actionable-items.csv`: `LedgerID,Priority,ChairFindingID,SourceReviewerFindingIDs,Severity,S0Subtype,Remedy,ExactPDFAnchor,DirectObservation,EvidenceStatus,MinimumEditEvidence,Dependency,Owner,Status,Verification`
- `93-current-ai-actionable-items.csv`: `AIFindingID,Impact,ExactPDFAnchor,DirectStyleObservation,MinimumEditingAction,Status,Verification`

The open required academic `LedgerID` set in `91-revision-ledger.csv` must exactly equal the `LedgerID` set in `93-current-actionable-items.csv`. The open `material`/`local` `AIFindingID` set in `91-ai-actionable-ledger.csv` must exactly equal the ID set in `93-current-ai-actionable-items.csv`. Duplicates, missing IDs, or extra IDs invalidate Stage S.

The matching rows agree losslessly field by field: both `93` CSV schemas are identical to their respective `91` schemas, and each `93` file is the exact open-row subset in source order. Any omitted column, same-ID content drift, reorder, missing row, or extra row invalidates Stage S. Every open `91` row with `Remedy=N` has exactly one `92` row; no other row may enter `92`. `EvidenceItemID` is continuous `N01...`, while `LedgerID`, `ChairFindingID`, and `Remedy=N` exactly match the linked `91` row. The N table in `92` and Stage S both project all nine CSV fields exactly.

Current-round academic and AI ledger `Status` values are limited to `open`, `closed`, `resolved`, `not required`, `not applicable`, or `N/A`; any other value is invalid. `91-revision-ledger.csv` additionally limits `Priority` to `P0`--`P3`, `Severity` to `S0`--`S3`, `Remedy` to `W/E/N/P`, and `EvidenceStatus` to `verified`, `partially verified`, `not verifiable from submitted PDF`, `deduplicated`, or `disputed`. A reviewer finding rejected by the submission-obligation gate does not enter `91`; it is preserved by its original `Rn-Fxx` ID in a direct Chair decision row with `Status=rejected`. `91-ai-actionable-ledger.csv` limits `Impact` to `material` or `local`; optional AI findings do not enter this CSV.

`LedgerID` and `ChairFindingID` are unique continuous sequences from `L01` and `C-F01`. `SourceReviewerFindingIDs` is a canonical duplicate-free comma-space list sorted by reviewer number and finding number. Every current reviewer `S0`--`S3` finding ID occurs exactly once in one of two mutually exclusive paths: a `91.SourceReviewerFindingIDs` cell, or a direct Chair decision row that cites the original `Rn-Fxx` and has `Status=rejected`. A direct reviewer-finding rejection may not be mixed with `Rn-Qxx` or `C-Fxx` in the same decision row, may not use another status, and produces no `C-Fxx`, `91`, `92`, or `93` row. Neither disappearance nor repeated adjudication is allowed. The chair's `Adjudicated findings` table is an exact field projection of the CSV, including `EvidenceStatus`. Disputed and not-verifiable Chair findings also appear in the chair's disagreement table. Every disagreement `Source item IDs` token must identify an actual current reviewer finding, current reviewer question, or current `ChairFindingID`; phantom IDs are invalid.

`Dependency` may name one or more current `LedgerID` values as explicit foreign
keys. Each referenced `Lnn` must exist in the same `91` master, must occur at
most once in that cell, and must not be the row's own ID; dependency cycles are
invalid. These validated LedgerID tokens are permitted only in the `Dependency`
column of the `91` and corresponding `93` academic tables. They remain forbidden
in unrelated columns or prose, so a real dependency is expressible without
weakening primary-key projection checks.

The chair citation cross-ledger gate is a real join, not a self-reported count. It has exactly the cited `ReferenceID` set, projects displayed labels and affected Pair IDs, serializes each citation identity/source and the fixed bibliography canonical-identity field list deterministically, derives agreement/conflict/resolution from `03`, `04`, and linked current `C-Fxx` rows, and recomputes all seven counts. A nonexistent reference, wrong Pair ID, unlinked conflict, or count drift invalidates the gate.

### Optional Stage-V prior-issues contract

- `stage-v-inputs/<name>-prior-issues.csv`: `PriorFindingID,PriorPDFSHA256,PriorPDFAnchor,Finding,RequiredClosureEvidence`

When optional Stage V runs, this CSV is the authoritative prior-finding row set. It is nonempty; all five fields are mandatory; `PriorFindingID` is a unique identifier matching `[A-Za-z][A-Za-z0-9._-]{0,127}`; every `PriorPDFSHA256` is the same 64-hex prior frozen-PDF identity; and `PriorPDFAnchor` names a positive physical page. The Stage-V Markdown closure table contains exactly these IDs once each and in CSV order. A phantom, omitted, duplicated, or reordered prior ID invalidates Stage V.

Every Stage-V prior input is copied into `stage-v-inputs/` and declared exactly once as `basename@SHA-256`. The validator requires the directory's regular-file set to equal the complete prior allowlist, hashes each file, rejects a missing or mismatched artifact, and verifies the same exact basename order in the V actor's `opened=[...]` receipt. The prior PDF and each of the six prior inventory/ledger inputs for a full regression audit use the same basename/hash contract. An author response is optional locator evidence and cannot replace or add rows to the prior-issues CSV.

The Stage-V iterative checklist is a deterministic projection rather than free prose: page counts/dispositions come from `02`, bibliography and citation verdict counts from `03`/`04`, open academic and AI rows from `91`, current reviewer `S0`--`S3` counts from the frozen R reports, and prior remainder from the CSV-reconciled closure rows. Any disagreement between the checklist and these frozen masters invalidates Stage V.

### Optional helper provenance

Every consumed helper writes `helpers/Hxx-provenance.json` with exactly these top-level fields:

`actor_id,round_id,retry_id,prompt_sha256,fresh_context_declaration,input_receipt_access_declaration,received_blocks,opened_inputs,tool,version,command_or_query,pdf_sha256_start,pdf_sha256_end,outputs,limitations,recipient_stages`

`received_blocks`, `opened_inputs`, `limitations`, and `recipient_stages` are arrays. The fresh-context string is canonical, and `input_receipt_access_declaration` must exactly serialize `received_blocks`, `opened_inputs`, and the three clean-access statements; prose cannot contradict or compensate for the arrays. `outputs` is a non-empty array of objects with exactly `file` and `sha256`; `file` is a neutral basename inside `helpers/`, and its hash is verified. The prompt and PDF hashes are 64 hexadecimal characters; both PDF hashes equal the frozen PDF. Every non-provenance file in `helpers/` must be registered by exactly one provenance record. For every declared recipient actor, the canonical opened list appends the provenance path and all output paths in deterministic helper/output order; every artifact signed by that actor must report those inputs. Unregistered, multiply registered, missing, path-traversing, unconsumed, or hash-mismatched helper output invalidates the bundle. If no helper is consumed, omit the `helpers/` directory.

## 3. Mandatory stage gates and final validation

Every actor with deterministic cross-artifact projections first runs the same
production pre-freeze materializer:

| Actor | Mandatory materialization command | Files it may rewrite mechanically |
|---|---|---|
| Doctoral R4 | `python rules/scripts/materialize_owner_outputs.py <exact-round-root> R4` | `04-citation-claim-audit-ledger.md`, `R4-comprehensive-review.md` receipt endpoint list |
| Doctoral R5 | `python rules/scripts/materialize_owner_outputs.py <exact-round-root> R5` | `02-page-layout-ledger.md`, `03-bibliography-audit-ledger.md`, `R5-comprehensive-review.md` receipt endpoint list |
| Master's R3 | `python rules/scripts/materialize_owner_outputs.py <exact-round-root> R3` | `02`, `03`, `04` Markdown masters and `R3-comprehensive-review.md` receipt endpoint list |
| C | `python rules/scripts/materialize_owner_outputs.py <exact-round-root> C` | deterministic tables/allowlist/one identical receipt in `90`, `91.md`, and `92.md`; never the three semantic Chair CSVs or free adjudication prose |
| S | `python rules/scripts/materialize_owner_outputs.py <exact-round-root> S` | all three wholly derived `93` outputs, including both open-row CSV subsets and every closed Markdown projection |

The materializer must exit `0` with first nonempty stdout `MATERIALIZED`. It is
run after every owned-CSV edit. It neither replaces nor wraps the following
read-only gate. Chair reruns it after any semantic `90`--`92` source change;
Stage S uses it to construct, rather than hand-copy, its three projection outputs.

Every substantive actor then runs its exact read-only gate before freezing or exiting:

| Actor | Mandatory command | Outputs the actor may correct before rerunning |
|---|---|---|
| P | `python rules/scripts/validate_stage_p_output.py <exact-round-root>` | `00-manifest.md`, `01-policy-basis.md`, and the five `00-*.csv` packet masters |
| Ordinary R reviewer | `python rules/scripts/validate_reviewer_output.py <exact-round-root> Rn` | that actor's `Rn-comprehensive-review.md` only |
| Doctoral R4 | `python rules/scripts/validate_r4_output.py <exact-round-root>` | `R4-comprehensive-review.md` and `04` Markdown/CSV only |
| Doctoral R5 | `python rules/scripts/validate_r5_output.py <exact-round-root>` | `R5-comprehensive-review.md`, `02`, `03`, and authorized page renders only |
| Master's R3 | `python rules/scripts/validate_master_r3_output.py <exact-round-root>` | `R3-comprehensive-review.md`, `02`, `03`, `04`, and authorized page renders only |
| AI | `python rules/scripts/validate_ai_output.py <exact-round-root>` | `05-ai-style-assessment.md` only |
| C | `python rules/scripts/validate_chair_output.py <exact-round-root>` | current Chair-owned `90`--`92` Markdown/CSV outputs only |
| S | `python rules/scripts/validate_summary_output.py <exact-round-root>` | `93-user-facing-summary.md` and both `93` CSV projections only |

Each gate passes only when it exits `0` and its first nonempty stdout line is exactly `PASS`. Do not skip, patch, mock, replace, suppress, or wrap a validator so its diagnostics disappear. The actor may repair only the owned outputs in the table and rerun within the same still-fresh turn. It must never edit the process envelope, frozen PDF, governing inputs, staged rules, Stage-P packet after P freezes, a peer artifact, or an upstream artifact. If a failure is attributable to any such frozen input, the actor stops and reports failure to Stage O. Once the actor exits/freeze occurs, or once post-S validation fails, the retry is immutable and must be globally quarantined/restarted under `clean-room-orchestration.md`.

For the doctoral R5 gate, this boundary is literal: R5 must not edit the Stage-P packet or any other frozen input. A packet/frozen-input diagnostic requires R5 to stop and report failure to Stage O; it is never repaired inside the R5 stage.

The ordinary reviewer and AI gates do not enumerate the round root or probe peer/downstream files. R4/R5/master's-R3 owner gates open only their exact packet and owned-ledger closure. Chair materialization and its gate use the closed C allowlist; the gate invokes the full validator's explicit `--pre-stage-s` mode, where `93`, `94`, and `95` are forbidden and no diagnostic is waived by message matching. Stage-S materialization and its gate open only the current R/AI/Chair summary sources, `91`/`92`, and S's three outputs; neither opens the PDF, packet, `02`--`04`, helpers, prior artifacts, or `95`. All validators are read-only and create no `95-bundle-validation.md`.

The R4 citation access receipt is closed. `ContentSourceOpened` is exactly one complete source URL except for the closed dangling-citation contract, where it and `ExactSourceLocator` remain blank. Any redirect, fallback, or failed route that was actually accessed is recorded in `DispositionEvidence` as `accessed endpoint: <URL>` followed only by a semicolon, newline, or field end. Each URL occurrence is checked independently and every marked auxiliary must itself pass the complete source-endpoint gate. Bare URLs in `PublicIdentifier`, attached propositions, locators, or unmarked disposition prose do not prove access. The R4 ledger/report receipt must contain every source and explicitly marked access endpoint once; an unrecorded receipt endpoint or an omitted recorded endpoint fails both scoped and full gates.

The R5/master's-R3 bibliography access receipt uses the same closure rule.
`EvidenceEndpoint` is the primary authoritative record for one field verdict;
every additional opened redirect, fallback, or failed route is marked in
`EvidenceNote` as `accessed endpoint: <URL>`. Bare URLs in rendered/canonical
metadata or unmarked notes do not authorize a receipt entry. The materializer
derives the exact duplicate-free receipt list from these authoritative fields;
the scoped and full gates reject both an extra receipt-only URL and an omitted
recorded URL.

Validator scripts and stdout are mechanical rule infrastructure only. They are never thesis/citation evidence, never decide whether a proposition is supported, and never replace packet neutrality, reviewer semantic judgment, page-level visual inspection, or Chair adjudication.

After Stage S has passed its scoped gate and frozen, Stage O runs the complete validator in an environment with `pypdf` and Pillow available (the bundled Codex workspace Python includes both; with `uv`, use `uv run --with pypdf --with pillow`):

```text
python scripts/validate_review_bundle.py <round-directory> --write-report <round-directory>/95-bundle-validation.md
```

When `--write-report` is supplied, its destination must be exactly the regular
in-root file `95-bundle-validation.md`. If that path already exists, it must be a
single-link regular file (`st_nlink == 1`), never a directory, symlink, hard
link, junction/reparse point, or other special entry. The validator checks this
before opening the bundle and again before an atomic no-following-alias replace;
every invalid destination is rejected without mutation. It never creates the
round directory, so a successful run cannot create an unallowlisted artifact or
rewrite an external alias after the closed-root decision.

The validator first performs a no-follow boundary preflight and refuses any symlink, NTFS junction, mount/reparse point, or other link-like entry at the round root or inside an allowed subdirectory. It then parses the frozen PDF and checks its real physical-page count; rejects basename collisions among the frozen PDF, governing files, skill references, generated artifacts, and closed-root directories; enforces a closed current-round root with no stale/extra file, directory, or special entry; independently binds the rendered bibliography span; re-extracts numeric-bracket candidates and unmatched glyphs; checks required files by degree type, deterministic ID sequences and source order, exact candidate page/context joins, complete Markdown schemas and full-field CSV projections, render-record sanity, mandatory bibliography fields and endpoint/date shape, citation content-endpoint/locator shape, allowed verdict/status values, page coverage, current academic/AI/N action reconciliation, complete Stage-S conclusions/current-only identity, chair question/disagreement and citation-gate consistency, optional Stage-V input hashes/prior-ID closure/checklist projections, and field-bound clean-room declarations. A nonzero exit code blocks a claim of completion. Review the printed failures; do not edit ledgers mechanically merely to satisfy counts.

## 4. Manual sign-off that validation cannot replace

The owning reviewer still signs:

- every page's actual visual disposition;
- every bibliography field's canonical value and evidence quality;
- every citation pair's exact attached proposition and source-content support;
- every finding's severity/remedy and grade consequence;
- every AI-style finding's contextual recurrence and impact;
- the chair's cross-ledger identity/support adjudication.

Counts, live URLs, hashes, and `pending=0` never establish semantic correctness by themselves.
