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
 R3 runs `python rules/scripts/materialize_owner_outputs.py <exact-reviewer-view-root> <actor-id>`
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

The validator then re-extracts every balanced square-bracket span containing at least one digit from every non-bibliography physical page of the frozen PDF with the bundled `pypdf` text extractor; spans may cross extracted line breaks and have no silent length cutoff. Stage P and every later PDF-reading or PDF-derived-packet scoped/full gate use the same bundled workspace Python for the round; Stage S is a PDF-free deterministic projection and does not import the extractor. Stage P records `PDF extraction runtime: pypdf=<pypdf.__version__>` in the canonical manifest identity block, and every validator compares it exactly with its own runtime before accepting the packet. Stage O must not launch an actor with an unpinned `uv --with pypdf` or another ad-hoc interpreter: a `pypdf` version change can alter extracted line breaks, raw offsets, bibliography slices, and adjacent windows even when the PDF bytes are identical. A future bundled-runtime upgrade is valid only for a newly generated packet whose complete round uses that one version. Page text is exactly the raw string returned by `PdfReader(path, strict=False).pages[i].extract_text() or ""`, with physical pages numbered from one. Candidate matching, bracket pairing, ordering, and window offsets operate on that unnormalized string. Only after a raw window is sliced are whitespace runs replaced by one ASCII space and the ends stripped; no Unicode normalization is applied.

Candidates are every nonempty nonnested `\[[^\[\]]+\]` span containing a decimal digit, ordered by physical page and raw start offset outside the derived bibliography span. Marker normalization removes whitespace, maps `，` to `,`, and maps `–`/`—` to `-`; the ledger's `Marker` cell must itself equal that canonical normalized marker, rather than relying on the validator to normalize a different stored spelling. Candidate context is the complete span plus up to 160 raw characters on each side. The stored `AdjacentPDFText` must equal the one deterministic normalized window byte for byte; a second normalization during comparison is forbidden because it could conceal ledger drift. `ExpandedNumbers` is the exact no-space ASCII-semicolon-separated serialization of the inclusive ordered expansion of one-to-four-digit integers/ranges, including descending ranges and duplicates and with ordinary integer rendering; all decimal/mixed/formula spans use exactly `N/A`. The candidate ledger contains exactly that sequence with continuous `BC0001...` IDs and the frozen-PDF hash. `Classification` is exactly `citation` or `non-citation`.

For every `non-citation` row, `ClassificationEvidence` is not prose. It must byte-for-byte equal the validator-derived token `non-citation-role:<canonical-role>`, where the closed roles are `non-integer-expression`, `math-domain`, `index-expression`, `coordinate`, `parameter-list`, `declared-numeric-collection`, `enumeration-run`, and `code-data-literal`. The validator derives the one role directly from the re-extracted frozen-PDF prefix, marker, and suffix; the actor cannot select a role by assertion. The predicates require strong local syntax: a non-pure-integer span with an actual decimal, operator, delimiter, function, or mathematical-symbol signal (not merely a malformed marker such as `[1a]`); membership, distribution-support, or explicitly bound domain syntax; an expression-continuing array index; an explicitly introduced integer coordinate; an explicitly named parameter-value list; an explicitly bound vector/array/shape/quantization-level collection; a headed bracket-number option run; or an assignment/return data literal. A bare positive-integer marker, a free-form claim such as “model/data numeric specification,” an identifier immediately followed by a bracketed number, a zero, or a repeated number is not sufficient. Thus `ACTOR[11]`, `MotionGPT[8]`, `运动图[9]`, `[4-5]`, or `[1-3,26,30]` remain citations unless their actual PDF syntax independently satisfies a closed role, while `x[1] = ...`, `t \in [0,1]`, `t\sim U[0,1]`, `top-k values [1,5,10]`, and an explicitly introduced quantization vector may be non-citations. An uncommon legitimate role outside this grammar is a Stage-P validation failure requiring a clean retry after the shared grammar and regression tests are extended; it cannot be resolved by free-form evidence or by silently deleting the candidate.

Every unmatched `[` or `]` on a non-bibliography page is derived in two deterministic steps. First, recognize the square endpoint of each high-confidence mixed-delimiter half-open interval `[a,b)` or `(a,b]`; those square offsets are emitted directly as visible-role glyphs and are excluded from both the ordinary square-bracket stack and numeric square-span candidates, so two half-open intervals cannot cross-pair into a false balanced citation candidate. Second, run the left-to-right LIFO page-level pairing scan on the remaining square glyphs. The direct mixed-delimiter endpoints, remaining opening glyphs, and unmatched closing glyphs are merged in page/raw-offset order and receive continuous `UBG0001...` rows. Each context is the raw slice `text[max(0, offset-160):min(len(text), offset+161)]` before the same whitespace normalization. The physical page, glyph, and normalized context must equal the validator extraction; the disposition explains the visible role and cannot claim that none were found. For the deterministically recognizable half-open interval forms, both endpoints use compact signed integer, decimal (including leading-decimal and scientific notation), percentage, infinity, Greek-symbol, or identifier syntax, with ASCII or fullwidth comma; the opening delimiter is not immediately preceded by an ASCII/Greek identifier-continuation character, which prevents function calls and array expressions such as `f(a,b]` or `matrix[a,b)` from being asserted as intervals. Such a recognized interval disposition must equal the closed token `visible-role:half-open-mathematical-interval`. Calling such a glyph an equation/display delimiter or using another free-form role is a semantic contradiction even when page, glyph, and context match. Other uncommon unmatched roles still require context-specific semantic sign-off rather than a template phrase. A positive manifest count equals this row count and names the sidecar; only a zero count permits an explicit none-found disposition. Any candidate or unmatched-glyph omission, extra row, reordering, page/marker/context mismatch, role/disposition contradiction, classification/mapping mismatch, cross-paired half-open interval, or obvious mathematical false positive invalidates Stage P.

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

For every PDF-derived bibliography page, re-extract the line-start entry labels
from that physical page. If `DominantContent` or `Evidence` asserts a bracketed
entry range, its endpoints must equal the page's actual minimum/maximum new
labels; a preceding entry continued from another page is described separately
and does not change the line-start range. A claimed range on a page with no new
entry label is invalid. This comparison is performed by both the owner-scoped
and full gates from the same frozen PDF/runtime.

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

Field extraction follows the complete cross-page `RenderedEntry`, not one
physical page in isolation. A URL split at a page boundary is still visibly
rendered and is reconstructed by removing extraction whitespace between its URL
tokens before deciding whether `Field=url` is absent. A primary evidence URL
cannot use its fragment, query, or an auxiliary endpoint to smuggle the missing
suffix of a visibly truncated path; if concatenating such text yields the
complete official path, the primary endpoint fails. A correct auxiliary route
does not repair that failure.

`CanonicalValue` represents the authoritative record, not a copy of PDF
line-wrap artifacts. For prose fields, an ASCII letter-hyphen-whitespace-letter
sequence such as `Con- ference` or `diffu- sion` is invalid canonical metadata.
The rendered scalar may contain such extraction hyphenation; exact comparison
normalizes a genuine line-wrap split before comparing it with the correctly
spelled canonical scalar. A real source hyphen remains adjacent to both word
parts and is preserved.

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

Immediately after that marker, the substantive evidence contains exactly one
semicolon-delimited clause sequence in this order: `pair role:`,
`source-stated claim:`, `source anchor:`, and `support boundary:`. `pair role`
is one of `full`, `subspan`, `premise`, `context`, `metadata`, or
`contradiction`. The boundary value contains exactly `supports=<nonempty> ||
does-not-support=<nonempty or N/A>`. The source claim and anchor are non-shell,
source-specific content; changing only the source title, URL, identifier, row
ID, hash, locator coordinate, or attached proposition cannot satisfy them.
Optional closed `accessed endpoint:` clauses follow the responsibility record.
Bare `Abstract`/`Section`/`Table` locators are therefore not self-sufficient:
the source anchor must relocate the actual statement, and a table-supported
number also identifies row, relevant columns, and any controlling
protocol/footnote.

That exact substring is also an atomic source-responsibility span. After only
its own displayed marker is removed, it cannot contain a marker mapped to a
different occurrence in an overlapping same-page Stage-P window, a running
header/footer, a detached printed-page digit, or more than 300 normalized
non-whitespace characters. For `Support=direct`, it cannot combine an external
source with the thesis's own method/table/experiment/result claim; the source-
attributed premise must be separated. An `Abstract`-only locator is invalid for
a detailed equation, theorem, metric definition, algorithmic step, or table
value.

The true Stage-P offsets, not marker text alone, define attachment and removal.
A comma/list/conjunction co-citation run may contain one indented extraction
line wrap; a semicolon, bare line break, blank line, or sentence boundary splits
the run. Bounded left/right introducers (`see`, `cf.`, `as shown in`, `见`,
`参见`, and their documented equivalents) may connect the smallest claim to the
marker. A marker-only or punctuation-only span fails. For spans above 200 and
at most 300 marker-stripped non-whitespace characters, crossing a genuine
sentence or strong-clause boundary is also a failure and the row must be split;
periods in ordinary abbreviations such as `e.g.` and `et al.` are not such
boundaries. The raw-offset check rejects blank-paragraph crossings and dynamic
running furniture such as decorated Roman/Arabic page counters or repeated
headers whose page number changes.

For those four support classes, identity-stripped `ExactSourceLocator` and
`DispositionEvidence` signatures are checked separately. The signature removes
URLs, DOI/arXiv/work/row IDs, numeric coordinates, binding markers, labeled
subjects, source-title interpolation, and the row's complete attached
proposition. A signature repeated
across at least 12 distinct `(ReferenceID, proposition)` units fails when it
spans at least six distinct references or eight distinct propositions. The
diagnostic reports the support class, distinct-reference count, unit count, and
threshold. Repeated occurrences of one work below that cross-source/
cross-proposition boundary remain available for reviewer judgment.

A concise structured locator is not exempt from thesis-scale repetition. One
identical locator covering at least 85 percent of one support class fails when
that class has at least 24 rows and the dominant locator spans at least 12
references and 18 propositions. Evidence bodies are additionally compared by
10-word and 24-CJK-character shingles; a shingle reused across at least 12
reference/proposition units, six references, and eight propositions fails even
when every row prepends a different title. These thresholds are minimum
mechanical alarms and do not replace semantic review of smaller repetitions.

An `unverifiable` row records a concrete source-specific failure or
content-insufficiency result. “Source-content access attempt” is not a locator,
and changing only the endpoint under one blanket environment-level waiver is
not a completed semantic audit. The validator permits repetition for multiple
occurrences of the same work but rejects a dominant identical waiver reused
across many distinct references.

The owning audit artifact and owning review report must list in their `public_endpoints=[...]` receipt every authoritative endpoint that their bibliography or citation master says was opened, including every valid marked auxiliary route. Each exact endpoint occurs once in the receipt. Declaring `[none]` while `EvidenceEndpoint`, `ContentSourceOpened`, or a valid `accessed endpoint:` marker contains a source is an invalid access record. A receipt-only endpoint is equally invalid. An `unverifiable` bibliography row still retains its complete attempted authoritative endpoint and contributes it to the receipt; it never invents a route or leaves `EvidenceEndpoint` blank.

### Owned-ledger report reconciliation

Every ledger owner report contains exactly one `Owned-ledger
finding/question reconciliation` table with headers `Report item ID` and
`Owned-ledger selectors`. It lists every current report finding/question exactly
once in report order, or is header-only when there are no items. The selector
cell is exactly `none` or a duplicate-free comma-space list drawn from:

- `02:page=Pnnnn` for one page row;
- `03:field=REFnnnn/<mandatory-field>` for one bibliography-field row;
- `04:pair=Cnnnn-Snn` for one citation Pair row;
- `04:reference=REFnnnn` for all current `04` rows of one reference.

Doctoral R4 may use only `04`, doctoral R5 only `02`/`03`, and master's R3 all
three. Mixed selector lists are ordered `02`, `03`, `04`, then by authoritative
CSV order. A `04:reference` selector cannot coexist with one of its expanded
`04:pair` selectors. The dedicated selector cell is the only additional place
where canonical Page/Reference/Pair IDs may appear outside their ordinary ledger
columns.

Normalize each owned ledger to its authoritative disposition: `02.Disposition`,
`03.FindingDisposition`, and `04.SeverityFinding`. Expand every report selector
and require exact set equality with the rows whose authoritative disposition is
that report item. Enforce the reverse join as well. Missing, extra, duplicate,
unknown, wrong-owner, wrong-ledger, or one-row/multiple-item links fail. A
`none`/`reasoned non-finding` row has no reciprocal report item and cannot be
selected. In `04`, an owner ID occurs only in `SeverityFinding`, never solely in
free-form `DispositionEvidence`, and it is mutually exclusive with `reasoned
non-finding:`. In `03`, `exact` and `legitimate N/A` require
`FindingDisposition=none`; `mismatch` requires one current owner finding/question;
`unverifiable` may be `none` or one owner item.

### Reviewer PDF-section anchors

The already validated `00-manifest.md` section map is the authority for explicit
thesis-section suffixes in reviewer Gate evidence, finding `Location`, and
question `Exact PDF anchor`. Recognize only `Section N.N[.N...]`, `Sec.
N.N[.N...]`, `§N.N[.N...]`, and `第N.N[.N...]节` (including fullwidth dots).
Do not interpret bare decimals or numbers labeled Table/Figure/Equation, DOI,
metric, or model version as sections. Build each section interval from its
heading page through the page immediately before the next equal-or-shallower
heading, bounded by the rendered thesis body. When an explicit section and a
canonical `physical p.<n>` appear in the same anchor segment, require the page
inside that interval; an explicitly named section must exist even when no page
can be paired. This rule never applies to `04.ExactSourceLocator`, whose section
belongs to an external cited source.

### Independent semantic-acceptance contract

After scoped `PASS` and Stage-O byte-copy, every frozen R/AI target has one
fresh acceptance pair in the finalized round under `06-semantic-acceptance/`:
`SA-<target>.md` and `SA-<target>.csv`. Before that SA-pair promotion, the actor
writes the same two basenames only at the root of its private target-specific
view; the private view must not contain a `06-semantic-acceptance/` directory.
Immediately before actor dispatch and while both outputs are absent, Stage O
runs the canonical SA `verify` command and retains its
`input_commitment.sha256` outside the private view and finalized round. Every
promotion must supply that exact value through the required
`--expected-input-commitment-sha256`; a baseline derived after dispatch is not
admissible. All opened inputs are named-stream-free single-link regular files
and their paths, identities, metadata, and bytes must still equal the prelaunch
commitment before and after exclusive copy. The scoped actor gate and finalized
`--set`/`--require-gate` gates independently repeat that invariant: every target
artifact and SA Markdown/CSV pair, plus the materialized root gate when
required, remains single-link, named-stream-free, and identity/byte stable
through terminal PASS. A hardlink, hidden NTFS stream, late replacement, or
late topology change invalidates the set. If an exclusive copy fails on Windows,
rollback disposes only the already-opened object whose identity and bytes match
the file created by that invocation; it never performs a check-then-path-unlink
that could erase a concurrently installed replacement.
The CSV is authoritative and has the exact schema:

`AcceptanceRowID,TargetUnitType,TargetUnitID,TargetArtifact,TargetArtifactSHA256,CheckClass,AcceptanceDisposition,EvidenceAnchor,SemanticBasis`

IDs are continuous `SA000001...` within each file. Target-unit type, check class,
and complete ordered row universe are closed as follows:

| Target unit type | Check class | Required units |
|---|---|---|
| `gate` | `semantic-coverage` | Gate A through Gate I for every R target |
| `chapter` | `whole-chapter` | every rendered numbered body chapter for every R target |
| `finding` | `evidence-support` | every current target `Rn-Fxx` |
| `question` | `scope-validity` | every current target `Rn-Qxx` |
| `verdict` | `grade-consistency` | exactly one `<target>-VERDICT` |
| `citation-pair` | `citation-claim` | every authoritative `04.PairID` for the citation owner |
| `page` | `rendered-page` | every authoritative `PageID` for the page owner; every Stage-P-authored-prose PageID for AI |
| `bibliography-field` | `bibliography-field` | every authoritative `REFnnnn/<field>` key for the bibliography owner |
| `ai-finding` | `style-evidence` | every current `AI-Fxx` |
| `ai-judgment` | `non-attribution` | exactly `AI-JUDGMENT` |

No row may be omitted, added, duplicated, reordered, left unchecked, or marked
with any disposition other than `pass`/`fail`. `PASS` is valid only when the
file is nonempty and contains no failed row. Every `TargetArtifactSHA256`
equals the current bytes. Unit-to-artifact binding is exact: report
gate/chapter/finding/question/verdict rows name the target report; citation pairs name
`04-citation-claim-audit-ledger.csv`; page-owner rows name the matching
`page-renders/Pnnnn.png`; bibliography rows name
`03-bibliography-audit-ledger.csv`; and AI rows name
`05-ai-style-assessment.md`.

The scoped SA CLI has exactly two mechanically completed outcomes. A nonempty,
fully covered pair with no failed row returns first-line `PASS` and exit `0` and
is the only pair Stage O may promote. A mechanically valid pair with one or more
honest failed rows returns first-line `VALID-FAIL` and exit `3`; Stage O
hash-verifies and preserves that private pair outside every substantive
allowlist, never invokes promotion or gate materialization for it, and
quarantines the entire retry. Any other first-line/exit combination is a schema,
hash, coverage, input, or execution failure rather than a completed semantic
outcome. Neither the acceptor nor Stage O rewrites a `VALID-FAIL` pair to seek a
more favorable result.

`EvidenceAnchor` and `SemanticBasis` are row-specific evidence, not ceremonial
sign-off. Physical-page units name an actual `physical p.<n>`; page-owner rows
are grounded in the corresponding PNG. Citation-pair rows for `direct`,
`partial`, `context-only`, `mismatch`, and every other ordinary sourced state
contain the pair's opened authoritative URL, exact source locator, exact
attached proposition, and exact singleton occurrence page from
`00-citation-inventory.csv`, and distinguish the source-stated claim from
thesis-local results. A documented non-dangling `Support=unverifiable` row whose
authoritative `04` source and locator are both blank must not invent either one;
instead its `SemanticBasis` binds exact semicolon-delimited `audited support:`,
`audited metadata status:`, and `authority access limitation:` values from that
`04` row, including its concrete source-specific access/content failure. A
dangling row likewise contains no source URL/locator and binds its exact
PDF-visible singleton location, displayed marker, absent `REF` entry, closed
sentinel, `Support=unverifiable`, `MetadataStatus=mismatch`, and authoritative
`04` disposition. Generic “unavailable” or “dangling citation” prose is not a
semantic basis. A passing detailed formula/definition/algorithm/table-value
responsibility cannot use an abstract-only source locator. Bibliography-field rows contain the authoritative
record endpoint actually checked plus exact semicolon-delimited
`rendered cue: <03 value>;`, `authority cue: <03 value>;`, and
`audited verdict: <03 verdict>;` bindings and an exact rendered-entry page;
a cross-page URL binds all contributing entry pages. Passing
finding/question/AI-finding rows match the target item's canonical singleton
page; failed rows may name a corrected page. Gate/finding/question/verdict and
AI rows identify concrete PDF evidence or counter-evidence appropriate to the
unit. Neither evidence field may assign a grade, command the Chair or defense
decision, or create/add/invent a thesis finding.

The acceptance threshold is reasonable support and admissibility, not personal
concurrence. A row may pass when the acceptor would choose a different
severity, weight, emphasis, or final recommendation, so long as the target
conclusion is concretely supported, bounded by the permitted evidence, does not
omit decisive counter-evidence, and requests a proportionate action. A normal
scholarly weighting disagreement is not itself a failed row. Conversely, an
honest unsupported or uncheckable conclusion remains `fail`; the acceptor must
not rewrite that judgment merely to make the pair pass.

For a passing `finding` row, `SemanticBasis` is exactly one compact canonical
JSON object (UTF-8 characters retained, no insignificant whitespace) in this
closed key order:

```json
{"assessment_standard":"reasonable-support-not-concurrence","premise_class":"<explicit-positive|bounded-inference|absence-after-search>","target_premise":"<exact parsed target Observation>","supporting_pdf_evidence":"<independently checked PDF fact including the finding's exact physical p.N>","whole_pdf_resolution":{"status":"<responsive-passages-reviewed|no-responsive-passage-found|not-applicable-positive-local-fact>","pages":["<physical p.N, only when responsive>"],"search_concepts":["<concrete concept used in the whole-PDF search>"],"detail":"<what the responsive passages establish, or what the complete search did not find>"},"residual_gap":{"status":"reasonably-supported","detail":"<why a reasonable reviewer may retain this bounded residual even if the acceptor would weight it differently>"},"action_delta":{"status":"<same-as-target-required-action|narrower-than-target-required-action|different-from-target-required-action>","detail":"<minimum still-unmet action>","independent_reason":"<acceptor's independent reason for that relation>"},"admissibility_result":"reasonably-supported"}
```

The outer key order is exactly `assessment_standard`, `premise_class`,
`target_premise`, `supporting_pdf_evidence`, `whole_pdf_resolution`,
`residual_gap`, `action_delta`, and `admissibility_result`. The two marker
values are exactly `reasonable-support-not-concurrence` and
`reasonably-supported`. `premise_class` is exactly `explicit-positive`,
`bounded-inference`, or `absence-after-search`; the target premise equals the
parsed finding `Observation`; and supporting evidence includes the finding's
exact singleton physical page. `whole_pdf_resolution` has the exact ordered keys
`status,pages,search_concepts,detail`; `residual_gap` has
`status,detail` and its status is exactly `reasonably-supported`; and
`action_delta` has `status,detail,independent_reason`. For
`no-responsive-passage-found`, `pages` is `[]` and `search_concepts` is
nonempty. `absence-after-search` requires that status; `bounded-inference` may
use it or `responsive-passages-reviewed`. The
`not-applicable-positive-local-fact` status is limited to `explicit-positive`
and uses empty `pages` and `search_concepts`. All substantive values must be
concrete and cannot use empty/`N/A`/`none`/Chinese-empty placeholders.

For a passing ordinary-reviewer `gate` row, `SemanticBasis` is exactly this
compact canonical JSON object in the shown key order:

```json
{"assessment_standard":"reasonable-support-not-concurrence","gate_id":"<exact Gate-A ... Gate-I target unit ID>","target_disposition":"<exact parser-canonical adequate|concern|unverifiable|n/a value; rendered N/A projects to n/a>","target_decisive_evidence":"<exact parsed Decisive evidence cell>","target_related_finding_ids":["<exact parsed related finding IDs in target order>"],"independent_pdf_assessment":{"supporting_pdf_evidence":"<independently rechecked evidence naming at least one physical page from the target decisive-evidence cell>","counterevidence_reviewed":"<concrete responsive neighboring or whole-PDF material checked>","admissibility_reason":"<independent reason the target Gate reading is reasonably supportable>"},"admissibility_result":"reasonably-supported"}
```

The outer key order is exactly `assessment_standard`, `gate_id`,
`target_disposition`, `target_decisive_evidence`,
`target_related_finding_ids`, `independent_pdf_assessment`, and
`admissibility_result`. The independent assessment has the exact ordered keys
`supporting_pdf_evidence,counterevidence_reviewed,admissibility_reason`. The
three target values and related-ID array bind the parser-canonical Gate row
exactly; a rendered target disposition `N/A` therefore binds as lowercase
`n/a` with an empty related-ID array. A `concern` Gate retains at least one
mapped actionable finding. The independent assessment is concrete and cannot
merely copy the target decisive-evidence cell.

For a passing ordinary-reviewer `question` row, `SemanticBasis` is exactly this
compact canonical JSON object in the shown key order:

```json
{"assessment_standard":"reasonable-support-not-concurrence","target_question":"<exact parsed Question cell>","target_why_unresolved":"<exact parsed Why unresolved cell>","target_needed_evidence":"<exact parsed Needed clarification/evidence cell>","target_page":"<exact parsed physical p.N anchor>","whole_pdf_resolution":{"status":"<responsive-passages-reviewed|no-responsive-passage-found>","pages":["<physical p.N for every responsive passage reviewed>"],"search_concepts":["<concrete concepts used across the frozen PDF>"],"detail":"<why the bounded question remains reasonably open after that check>"},"admissibility_result":"reasonably-supported"}
```

The outer key order is exactly `assessment_standard`, `target_question`,
`target_why_unresolved`, `target_needed_evidence`, `target_page`,
`whole_pdf_resolution`, and `admissibility_result`. All four target strings
bind the parsed Question row exactly. For `responsive-passages-reviewed`, both
`pages` and `search_concepts` are nonempty; for
`no-responsive-passage-found`, `pages` is empty and `search_concepts` is
nonempty. Generic acceptance prose is invalid for either Gate or Question.

A passing ordinary reviewer `verdict` row uses one compact canonical JSON
object with the exact ordered keys `gate_disposition_profile`,
`actionable_finding_profile`, `synthesis_cue`, `target_verdict`, and
`coherence_result`; each value exactly equals the validator's canonical JSON
projection string for the frozen report.
After URL, hash, IDs, numbers, and whitespace are normalized, the same basis may
not be copied across twelve or more units of one type. This mechanical alarm is
only a minimum: a smaller repeated template, title interpolation, a generic
“checked and supported” assertion, or the target actor's own rationale copied
without independent comparison remains a semantic acceptance failure.

Each Markdown acceptance binds its exact target-artifact list and hashes, CSV
row count, failure count, prompt hash, PDF start/end hash, fresh-context
declaration, and closed receipt. Its only overall value is `PASS` or `FAIL`; it
contains no thesis finding, grade, defense recommendation, or Chair decision.
The exact isolated input allowlist is target-specific and excludes peer reports,
peer acceptances, Chair/Stage-S files, old rounds, conversation context, thesis
source, `.bib`, Git, sibling repositories, and private evidence. Any input named
in the acceptance evidence must occur in that receipt; public endpoints cannot
exceed the target's own authorized endpoint set.

When and only when every required target pair independently passes, Stage O
materializes `06-semantic-acceptance-gate.json`. Its JSON value equals the
validator-derived canonical v2 object exactly: schema tag, round/retry/PDF
hash, exact `00-process-parameters.json` SHA-256, the degree-appropriate closed
`SA-*` actor-prompt hash map copied from that process, the ordered target map,
each target-artifact hash map, acceptance Markdown/CSV hashes, coverage row
count, target status `PASS`, and overall `PASS`. It has no free text or semantic
details. During set materialization and final full validation, the set
validator requires the directory's regular-file set to equal exactly all
required pairs, recomputes every hash, and rejects a missing/extra target or
failed row.

The Chair receives only this hash gate; its isolated view must not contain the
`06-semantic-acceptance/` directory or the R5 page-render tree. Its scoped gate
therefore exactly recomputes the process-file hash, `SA-*` prompt-map
projection, every C-visible target-artifact hash, and expected coverage counts,
while treating each `acceptance_md_sha256`/`acceptance_csv_sha256` and R5 render
hash only as a closed 64-hex Stage-O transport commitment. It must not claim to
have recomputed bytes it is forbidden to see. A different well-formed private-
file/render hash cannot be distinguished by the Chair alone; after Stage S,
the final full validator must open the private directory/render tree and
revalidate those hashes and the complete acceptance content.
Stage S receives neither the gate nor that directory.

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

### Reserved future Stage-V prior-issues contract

- `stage-v-inputs/<name>-prior-issues.csv`: `PriorFindingID,PriorPDFSHA256,PriorPDFAnchor,Finding,RequiredClosureEvidence`

Production runner v1 rejects Stage V and every prior-issue input. The schema below is reserved for a future extension with its own complete prompt/view/transport/promotion/runner contract; it is not an enabled current-round input. In such an extension, this CSV would be the authoritative prior-finding row set. It would be nonempty; all five fields would be mandatory; `PriorFindingID` would be a unique identifier matching `[A-Za-z][A-Za-z0-9._-]{0,127}`; every `PriorPDFSHA256` would be the same 64-hex prior frozen-PDF identity; and `PriorPDFAnchor` would name a positive physical page. The Stage-V Markdown closure table would have to match those IDs exactly once each and in CSV order.

Every Stage-V prior input is copied into `stage-v-inputs/` and declared exactly once as `basename@SHA-256`. The validator requires the directory's regular-file set to equal the complete prior allowlist, hashes each file, rejects a missing or mismatched artifact, and verifies the same exact basename order in the V actor's `opened=[...]` receipt. The prior PDF and each of the six prior inventory/ledger inputs for a full regression audit use the same basename/hash contract. An author response is optional locator evidence and cannot replace or add rows to the prior-issues CSV.

The Stage-V iterative checklist is a deterministic projection rather than free prose: page counts/dispositions come from `02`, bibliography and citation verdict counts from `03`/`04`, open academic and AI rows from `91`, current reviewer `S0`--`S3` counts from the frozen R reports, and prior remainder from the CSV-reconciled closure rows. Any disagreement between the checklist and these frozen masters invalidates Stage V.

### Reserved future helper provenance

Production runner v1 rejects H actors, `helpers/`, and `--helper-input`. The
following dormant schema is a design note for a future extension and cannot
authorize current production input. Any such extension would require each
consumed helper to write `helpers/Hxx-provenance.json` with exactly these
top-level fields:

`actor_id,round_id,retry_id,prompt_sha256,fresh_context_declaration,input_receipt_access_declaration,received_blocks,opened_inputs,tool,version,command_or_query,pdf_sha256_start,pdf_sha256_end,outputs,limitations,recipient_stages`

`received_blocks`, `opened_inputs`, `limitations`, and `recipient_stages` are arrays. The fresh-context string is canonical, and `input_receipt_access_declaration` must exactly serialize `received_blocks`, `opened_inputs`, and the three clean-access statements; prose cannot contradict or compensate for the arrays. `outputs` is a non-empty array of objects with exactly `file` and `sha256`; `file` is a neutral basename inside `helpers/`, and its hash is verified. The prompt and PDF hashes are 64 hexadecimal characters; both PDF hashes equal the frozen PDF. Every non-provenance file in `helpers/` must be registered by exactly one provenance record. For every declared recipient actor, the canonical opened list appends the provenance path and all output paths in deterministic helper/output order; every artifact signed by that actor must report those inputs. Unregistered, multiply registered, missing, path-traversing, unconsumed, or hash-mismatched helper output invalidates the bundle. If no helper is consumed, omit the `helpers/` directory.

No production-v1 Chair command contains a helper argument. Dormant
helper-aware validator branches remain non-authoritative until a future runner
implements the complete extension described above.

## 3. Mandatory stage gates and final validation

Every actor with deterministic cross-artifact projections first runs the same
production pre-freeze materializer:

| Actor | Mandatory materialization command | Files it may rewrite mechanically |
|---|---|---|
| Doctoral R4 | `python rules/scripts/materialize_owner_outputs.py <exact-reviewer-view-root> R4` | `04-citation-claim-audit-ledger.md`, `R4-comprehensive-review.md` receipt endpoint list |
| Doctoral R5 | `python rules/scripts/materialize_owner_outputs.py <exact-reviewer-view-root> R5` | `02-page-layout-ledger.md`, `03-bibliography-audit-ledger.md`, `R5-comprehensive-review.md` receipt endpoint list |
| Master's R3 | `python rules/scripts/materialize_owner_outputs.py <exact-reviewer-view-root> R3` | `02`, `03`, `04` Markdown masters and `R3-comprehensive-review.md` receipt endpoint list |
| Stage O after all SA targets pass | `"<absolute-bundled-python>" -B scripts/stage_o_runner.py close-sa-set --run-root <absolute-run-root> --expected-transition-token <previous-token>` | Runner-owned creation of `06-semantic-acceptance-gate.json` only; no R/AI/SA semantic artifact may be edited |
| C | `python rules/scripts/materialize_owner_outputs.py <exact-stage-c-view-root> C` | deterministic tables/allowlist/one identical receipt in `90`, `91.md`, and `92.md`; never the three semantic Chair CSVs or free adjudication prose |
| S | `python rules/scripts/materialize_owner_outputs.py <exact-stage-s-view-root> S` | all three wholly derived `93` outputs, including both open-row CSV subsets and every closed Markdown projection |

The materializer must exit `0` with first nonempty stdout `MATERIALIZED`. It is
run after every owned-CSV edit. It neither replaces nor wraps the following
read-only gate. Chair reruns it after any semantic `90`--`92` source change;
Stage S uses it to construct, rather than hand-copy, its three projection outputs.

Every substantive actor then runs its exact read-only gate before freezing or exiting:

| Actor | Mandatory command | Outputs the actor may correct before rerunning |
|---|---|---|
| P | `python rules/scripts/validate_stage_p_output.py <exact-stage-p-view-root>` | `00-manifest.md`, `01-policy-basis.md`, and the five `00-*.csv` packet masters |
| Ordinary R reviewer | `python rules/scripts/validate_reviewer_output.py <exact-reviewer-view-root> Rn` | that actor's `Rn-comprehensive-review.md` only |
| Doctoral R4 | `python rules/scripts/validate_r4_output.py <exact-reviewer-view-root>` | `R4-comprehensive-review.md` and `04` Markdown/CSV only |
| Doctoral R5 | `python rules/scripts/validate_r5_output.py <exact-reviewer-view-root>` | `R5-comprehensive-review.md`, `02`, `03`, and authorized page renders only |
| Master's R3 | `python rules/scripts/validate_master_r3_output.py <exact-reviewer-view-root>` | `R3-comprehensive-review.md`, `02`, `03`, `04`, and authorized page renders only |
| AI | `python rules/scripts/validate_ai_output.py <exact-stage-ai-view-root>` | `05-ai-style-assessment.md` only |
| Each `SA-<target>` | `python rules/scripts/validate_semantic_acceptance_output.py <exact-SA-view> <target>` | that acceptor's own `SA-<target>.md` and `.csv` only; never the frozen target |
| Stage O SA-set closure | `"<absolute-bundled-python>" -B scripts/stage_o_runner.py close-sa-set --run-root <absolute-run-root> --expected-transition-token <previous-token>` | none; the runner invokes the pinned validator/materializer internally and any failure invalidates the retry |
| C | `python rules/scripts/validate_chair_output.py <exact-stage-c-view-root>` | exact unified C private view and current Chair-owned `90`--`92` Markdown/CSV outputs only; production v1 permits no helper flag |
| S | `python rules/scripts/validate_summary_output.py <exact-stage-s-view-root>` | exact unified S private view, `93-user-facing-summary.md`, and both `93` CSV projections only |

Each gate passes only when it exits `0` and its first nonempty stdout line is exactly `PASS`. Do not skip, patch, mock, replace, suppress, or wrap a validator so its diagnostics disappear. The actor may repair only the owned outputs in the table and rerun within the same still-fresh turn. It must never edit the process envelope, frozen PDF, governing inputs, staged rules, Stage-P packet after P freezes, a peer artifact, or an upstream artifact. If a failure is attributable to any such frozen input, the actor stops and reports failure to Stage O. Once the actor exits/freeze occurs, or once post-S validation fails, the retry is immutable and must be globally quarantined/restarted under `clean-room-orchestration.md`.

For the doctoral R5 gate, this boundary is literal: R5 must not edit the Stage-P packet or any other frozen input. A packet/frozen-input diagnostic requires R5 to stop and report failure to Stage O; it is never repaired inside the R5 stage.

The ordinary reviewer and AI gates do not enumerate the round root or probe peer/downstream files. R4/R5/master's-R3 owner gates open only their exact packet and owned-ledger closure. Each SA scoped gate opens one closed target-specific view and no peer acceptance. Stage O alone checks the complete SA set and materializes its hash gate. Chair materialization and its gate run in the exact unified C private view, which contains the hash-only gate but no individual SA files, page-render tree, or helper; the C gate treats private-SA and R5-render hashes as Stage-O transport commitments and leaves byte recomputation to the final full validator. Stage-S materialization and its gate run in the exact unified S private view and open only the current R/AI/Chair summary sources, `91`/`92`, and S's three outputs. After parsing the process envelope, each private-view gate rejects any extra/missing tree entry before opening other substantive sources, then serves every semantic CSV/Markdown read from captured stable bytes and repeats its topology check at the terminal boundary. Every member is single-link, named-stream-free, and identity/byte stable through scoped PASS. S never opens the PDF, packet, `02`--`04`, individual SA files, SA hash gate, helpers, prior artifacts, or `95`; C opens only its canonical PDF/packet/ledger/report inputs. All validators except the two explicitly named deterministic materializers are read-only and create no `95-bundle-validation.md`. Stage O rechecks the externally retained prelaunch input commitment before promoting only each actor's owned outputs.

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

After Stage S has passed its scoped gate and frozen, production Stage O invokes
the complete validator only through the authoritative runner transition, using
the Python executable and validator bytes pinned at bootstrap:

```text
"<absolute-bundled-python>" -B scripts/stage_o_runner.py finalize --run-root <absolute-run-root> --expected-transition-token <previous-token>
```

The runner internally executes `validate_review_bundle.py` with the exact
final-round path and exclusive `95-bundle-validation.md` destination. A direct
validator invocation is permitted only as read-only diagnosis when it omits
`--write-report`; it cannot advance the Stage-O event chain or authorize
delivery.

When `--write-report` is supplied, its destination must be exactly the regular
in-root file `95-bundle-validation.md`. If that path already exists, it must be a
single-link regular file (`st_nlink == 1`), never a directory, symlink, hard
link, junction/reparse point, or other special entry. The validator checks this
before opening the bundle and again before an atomic no-following-alias replace;
every invalid destination is rejected without mutation. It never creates the
round directory, so a successful run cannot create an unallowlisted artifact or
rewrite an external alias after the closed-root decision.

The validator first performs a no-follow boundary preflight and refuses any symlink, NTFS junction, mount/reparse point, or other link-like entry at the round root or inside an allowed subdirectory. It then parses the frozen PDF and checks its real physical-page count; rejects basename collisions among the frozen PDF, governing files, skill references, generated artifacts, and closed-root directories; enforces a closed current-round root with no stale/extra file, directory, or special entry; independently binds the rendered bibliography span; requires a canonical authored-prose physical-page set and rejects omission of any PDF-derived independent substantive `序言`/`前言`/`Preface`/`Foreword` page or sustained authored contribution/explanatory prose detected in rendered back matter (metadata exclusions are span-level, never whole-page); re-extracts numeric-bracket candidates and unmatched glyphs; checks required files by degree type, deterministic ID sequences and source order, exact candidate page/context joins, complete Markdown schemas and full-field CSV projections, render-record sanity, mandatory bibliography fields and endpoint/date shape, citation content-endpoint/locator shape, allowed verdict/status values, page coverage, current academic/AI/N action reconciliation, complete Stage-S conclusions/current-only identity, chair question/disagreement and citation-gate consistency, optional Stage-V input hashes/prior-ID closure/checklist projections, and field-bound clean-room declarations. A nonzero exit code blocks a claim of completion. Review the printed failures; do not edit ledgers mechanically merely to satisfy counts.

## 4. Manual sign-off that validation cannot replace

The owning reviewer still signs:

- every page's actual visual disposition;
- every bibliography field's canonical value and evidence quality;
- every citation pair's exact attached proposition and source-content support;
- every finding's severity/remedy and grade consequence;
- every AI-style finding's contextual recurrence and impact;
- the chair's cross-ledger identity/support adjudication.

Counts, live URLs, hashes, and `pending=0` never establish semantic correctness by themselves.
