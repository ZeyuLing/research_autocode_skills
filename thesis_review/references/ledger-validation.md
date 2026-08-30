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
- In final `02-page-layout-ledger.csv`, every cell is nonempty and nonplaceholder except `PrintedPage`, which may be blank only when no printed label is rendered. In `03-bibliography-audit-ledger.csv`, every cell is nonempty and nonplaceholder except `EvidenceEndpoint`, which may be blank only for a documented `unverifiable` row whose `EvidenceNote` records the attempted official route/query/date and negative result. Whitespace-only cells are blank; use an explicit contract value such as `N/A` only where that field's closed vocabulary permits it.
- Process large ledgers in deterministic ID ranges and checkpoint batches; concatenate only after duplicate/missing/extra validation.
- Every sidecar records the frozen PDF SHA-256 in its companion Markdown report and, when practical, in a `PDFSHA256` column.

For every authoritative-CSV-to-Markdown projection below, a scalar cell uses
the exact CSV string after CRLF/CR normalization to LF and JSON string escaping
with Unicode retained, but with the surrounding JSON quotes omitted. Thus
ordinary values remain ordinary text, a real newline becomes `\n`, and a
literal backslash remains distinguishable from that newline escape. After this
serialization, escape each literal Markdown table delimiter `|` as `\|` in the
Markdown source; the validator decodes only that table escape before comparing.
Markdown table padding is not data, so authoritative CSV values that depend on
leading or trailing whitespace cannot reconcile. Headers are case-sensitive and
must use the documented spelling and order. Rows use deterministic ID order,
and every projected non-hash cell is compared, not only the ID. `PDFSHA256` is
bound by the Markdown checksum declaration and validated on every authoritative
CSV row rather than duplicated as a table column.

## 2. Required machine-readable contracts

### Stage-P inventories

- `00-page-inventory.csv`: `PageID,PhysicalPage,PrintedPage,Region,MechanicalSignals,PDFSHA256`
- `00-bibliography-inventory.csv`: `ReferenceID,DisplayedLabel,RenderedEntry,Cited,PDFSHA256`
- `00-citation-candidate-ledger.csv`: `CandidateID,PhysicalPage,Marker,ExpandedNumbers,Classification,ClassificationEvidence,MappedOccurrenceID,AdjacentPDFText,PDFSHA256`
- `00-unmatched-bracket-ledger.csv`: `GlyphID,PhysicalPage,Glyph,AdjacentPDFText,Disposition,PDFSHA256`
- `00-citation-inventory.csv`: `PairID,OccurrenceID,PDFLocation,DisplayedReferenceID,AdjacentPDFText,PDFSHA256`

The validator independently derives the bibliography's contiguous physical-page span from the unique **longest** rendered line-start entry run `[1]...[N]`, requires its length to equal the bibliography inventory, and requires a rendered `References`/`参考文献` heading on the run's first page; a free-text `Region` value or an isolated body `[1]` cannot remove an arbitrary body page from extraction. `RenderedEntry` is mechanically bound row by row: for `[n]`, take the raw extracted text after that line-start label through the raw start of `[n+1]`; when the boundary crosses pages, join the current-page suffix, every intervening page, and the next-page prefix with LF; for `[N]`, continue through the end of the last bibliography page. Apply only `re.sub(r"\s+", " ", value).strip()` to that slice. The resulting string—not an independently retyped citation—must equal `RenderedEntry` byte for byte. An exact duplicate between two correctly extracted rows remains in the packet as a possible thesis defect for the bibliography reviewer; packet validation must not erase or reject it merely for being duplicated.

The validator then re-extracts every balanced square-bracket span containing at least one digit from every non-bibliography physical page of the frozen PDF with the bundled `pypdf` text extractor; spans may cross extracted line breaks and have no silent length cutoff. Page text is exactly the raw string returned by `PdfReader(path, strict=False).pages[i].extract_text() or ""`, with physical pages numbered from one. Candidate matching, bracket pairing, ordering, and window offsets operate on that unnormalized string. Only after a raw window is sliced are whitespace runs replaced by one ASCII space and the ends stripped; no Unicode normalization is applied.

Candidates are every nonempty nonnested `\[[^\[\]]+\]` span containing a decimal digit, ordered by physical page and raw start offset outside the derived bibliography span. Marker normalization removes whitespace, maps `，` to `,`, and maps `–`/`—` to `-`; the ledger's `Marker` cell must itself equal that canonical normalized marker, rather than relying on the validator to normalize a different stored spelling. Candidate context is the complete span plus up to 160 raw characters on each side. The stored `AdjacentPDFText` must equal the one deterministic normalized window byte for byte; a second normalization during comparison is forbidden because it could conceal ledger drift. `ExpandedNumbers` is the exact no-space ASCII-semicolon-separated serialization of the inclusive ordered expansion of one-to-four-digit integers/ranges, including descending ranges and duplicates and with ordinary integer rendering; all decimal/mixed/formula spans use exactly `N/A`. The candidate ledger contains exactly that sequence with continuous `BC0001...` IDs and the frozen-PDF hash. `Classification` is exactly `citation` or `non-citation`; `ClassificationEvidence` identifies the local grammatical role rather than merely saying “checked,” `citation`, or `non-citation`. Decimal/mixed/formula spans, zero-bearing markers, duplicate-number vectors, and markers used immediately as mathematical set/interval membership or explicitly introduced as an array/vector/quantization-level list cannot be classified as citations.

Every unmatched `[` or `]` on a non-bibliography page is derived by one left-to-right LIFO page-level pairing scan. Remaining opening glyphs and unmatched closing glyphs are merged in page/raw-offset order and receive continuous `UBG0001...` rows. Each context is the raw slice `text[max(0, offset-160):min(len(text), offset+161)]` before the same whitespace normalization. The physical page, glyph, and normalized context must equal the validator extraction; the disposition explains the visible role and cannot claim that none were found. A positive manifest count equals this row count and names the sidecar; only a zero count permits an explicit none-found disposition. Any candidate or unmatched-glyph omission, extra row, reordering, page/marker/context mismatch, classification/mapping mismatch, or obvious mathematical false positive invalidates Stage P.

The Stage-P citation inventory is mechanical after candidate disambiguation. Citation-classified candidates alone receive continuous `Cnnnn` occurrence IDs; a non-citation candidate consumes no occurrence ID. Expanded element `n` at one-based source ordinal `k` creates exactly one Pair row whose ID is `Cnnnn-S{k:02d}` (`S01`--`S99`, then `S100` and wider ordinary decimal rendering through `S9999`) and whose `DisplayedReferenceID` is `REF{n:04d}`. Pair rows preserve the expanded-vector order; every occurrence maps to exactly one candidate and every candidate occurrence maps back. `PDFLocation` names the candidate's valid physical page, and `AdjacentPDFText` copies the candidate's deterministic normalized extraction window exactly; it is an anchor, not a semantic proposition verdict. If a displayed citation number has no rendered bibliography row, retain that Pair row unchanged: the dangling citation is a paper defect for reviewer audit, not a reason for the neutral packet builder to delete the evidence or fail its own extraction gate.

### Page audit

- `02-page-layout-ledger.csv`: `PageID,PhysicalPage,PrintedPage,Region,DominantContent,Signals,InspectionModeScale,RenderDPI,RenderArtifactIDHash,NeighborPagesChecked,Disposition,Evidence,PDFSHA256`

The Page-ID set must exactly equal `00-page-inventory.csv`; `PhysicalPage` must form `1..N` with no gaps or duplicates; and `Pnnnn` must map to physical page `nnnn` in both inventories. Every suspect page uses `full-scale`; every page has a non-empty disposition and inspection mode. A final `Disposition` is exactly `clean`, `intentional`, or `finding Rn-Fxx` for the assigned page owner; `recheck after edit`, `pending`, `unchecked`, `open`, and `unresolved` are invalid final states. Every finding reference resolves to an actual current owner finding. The owner report's actionable layout count is the number of distinct referenced finding IDs, so repeated page rows for one finding count once. `RenderDPI` normally follows the 160--200 dpi audit target; the validator accepts 120--600 only as a mechanical sanity range. Retain one decodable PNG as `page-renders/<PageID>.png`; its dimensions must match the frozen PDF page at the declared DPI, and `RenderArtifactIDHash` is that file's exact 64-hex SHA-256, optionally prefixed by the matching PageID. The `02` Markdown table uses exactly the twelve headers in `rendered-pagination-audit.md`, sorts by `PageID`, and projects `PageID,PhysicalPage,PrintedPage,Region,DominantContent,Signals,InspectionModeScale,RenderDPI,RenderArtifactIDHash,NeighborPagesChecked,Disposition,Evidence` field by field. Each Markdown master must contain exactly one complete pipe table with its documented ID header, an immediately following separator row, consistent column counts, and every corresponding CSV ID exactly once in that table's ID column. Ledger IDs must not recur in prose, code fences, or an unrelated table/column; the matching PageID prefix inside its own `Render artifact ID/hash` cell is the sole permitted repetition. Prose mentions and standalone pipe rows do not count as ledger rows and invalidate the projection.

### Bibliography audit

- `03-bibliography-audit-ledger.csv`: `ReferenceID,DisplayedLabel,Cited,Field,RenderedValue,CanonicalValue,Verdict,EvidenceEndpoint,EndpointType,CheckedAt,EvidenceNote,FindingDisposition,PDFSHA256`

For each `ReferenceID`, the `(ReferenceID,Field)` key is unique and the mandatory field set is exactly:

`type,title,ordered_authors,year,venue,publication_status,volume,issue,pages_or_article_number,doi,arxiv_id,arxiv_version,url,access_date,isbn_or_other_persistent_id,existence,retraction_withdrawal_correction_superseding`.

`Verdict` is one of `exact`, `mismatch`, `legitimate N/A`, or `unverifiable`. A non-`unverifiable` row records one complete `http(s)` authoritative endpoint. `CheckedAt` is an ISO-8601 date or datetime. For `unverifiable`, `EvidenceNote` records the attempted official route/query/date and negative/access result when no authoritative endpoint exists, in which case `EvidenceEndpoint` may be blank. For `mismatch`, the entire `FindingDisposition` cell is exactly one current owning-reviewer `Rn-Fxx` or `Rn-Qxx` ID—no prefix, suffix, free prose, second ID, `none`, `N/A`, or mixture with any exemption phrase. Canonical `REFnnnn` tokens occur only in the `ReferenceID` column/cell; they never recur in another CSV field, prose, code fence, or unrelated Markdown column.

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

The Pair-ID set and row order must exactly equal `00-citation-inventory.csv`; ordering is numeric by occurrence/source ordinal, so `S99` precedes `S100`. `Support` is one of `direct`, `partial`, `context-only`, `mismatch`, `unverifiable`, or `not-needed`, and `MetadataStatus` is one of `verified`, `mismatch`, or `unverifiable`. A substantive support verdict other than `unverifiable` requires an `http(s)` content endpoint in `ContentSourceOpened` and a structured locator such as `page 14`, `section 3.2`, `Table 2`, `Figure 4`, `Equation 7`, `Abstract`, or `publisher record: DOI ...`; a bare word such as `section` is invalid. Publication metadata alone is acceptable only when the attached proposition is publication metadata. A `ReferenceID` absent from the rendered bibliography uses exactly `Support=unverifiable`, `MetadataStatus=mismatch`, `PublicIdentifier=no rendered bibliography entry`, blank `ContentSourceOpened`/`ExactSourceLocator`, and a current owning-reviewer finding/question link. The Markdown projection uses the exact twelve headers in `citation-audit.md`, sorts by numeric Pair-ID ordinals, and compares every projected field. `Displayed label` is the exact `00-bibliography-inventory.csv` label for an existing row; for a dangling `REFnnnn`, it is `[n]` derived from the frozen PDF marker. `Content source opened and exact locator` is compact JSON with exact key order `{"content_source_opened":"<ContentSourceOpened>","exact_source_locator":"<ExactSourceLocator>"}`; all other non-hash CSV fields map one-to-one to their named Markdown column. Every CSV PairID must occur exactly once as a complete table cell.

The owning audit artifact and owning review report must list in their `public_endpoints=[...]` receipt every nonblank authoritative endpoint that their bibliography or citation master says was opened. Declaring `[none]` while `EvidenceEndpoint` or `ContentSourceOpened` contains a source is an invalid access record. A documented `unverifiable` row may leave the endpoint blank only under the explicit inaccessible-route contract; it creates no fictional receipt entry.

### Chair and summary reconciliation

- `91-revision-ledger.csv`: `LedgerID,Priority,ChairFindingID,SourceReviewerFindingIDs,Severity,S0Subtype,Remedy,ExactPDFAnchor,DirectObservation,EvidenceStatus,MinimumEditEvidence,Dependency,Owner,Status,Verification`
- `91-ai-actionable-ledger.csv`: `AIFindingID,Impact,ExactPDFAnchor,DirectStyleObservation,MinimumEditingAction,Status,Verification`
- `92-new-evidence-or-experiments.csv`: `EvidenceItemID,LedgerID,ChairFindingID,Remedy,Item,ClaimThatDependsOnIt,WhyWritingIsInsufficient,MinimumViableEvidence,ConsequenceIfUnavailable`
- `93-current-actionable-items.csv`: `LedgerID,Priority,ChairFindingID,SourceReviewerFindingIDs,Severity,S0Subtype,Remedy,ExactPDFAnchor,DirectObservation,EvidenceStatus,MinimumEditEvidence,Dependency,Owner,Status,Verification`
- `93-current-ai-actionable-items.csv`: `AIFindingID,Impact,ExactPDFAnchor,DirectStyleObservation,MinimumEditingAction,Status,Verification`

The open required academic `LedgerID` set in `91-revision-ledger.csv` must exactly equal the `LedgerID` set in `93-current-actionable-items.csv`. The open `material`/`local` `AIFindingID` set in `91-ai-actionable-ledger.csv` must exactly equal the ID set in `93-current-ai-actionable-items.csv`. Duplicates, missing IDs, or extra IDs invalidate Stage S.

The matching rows agree losslessly field by field: both `93` CSV schemas are identical to their respective `91` schemas, and each `93` file is the exact open-row subset in source order. Any omitted column, same-ID content drift, reorder, missing row, or extra row invalidates Stage S. Every open `91` row with `Remedy=N` has exactly one `92` row; no other row may enter `92`. `EvidenceItemID` is continuous `N01...`, while `LedgerID`, `ChairFindingID`, and `Remedy=N` exactly match the linked `91` row. The N table in `92` and Stage S both project all nine CSV fields exactly.

Current-round academic and AI ledger `Status` values are limited to `open`, `closed`, `resolved`, `not required`, `not applicable`, or `N/A`; any other value is invalid. `91-revision-ledger.csv` additionally limits `Priority` to `P0`--`P3`, `Severity` to `S0`--`S3`, `Remedy` to `W/E/N/P`, and `EvidenceStatus` to `verified`, `partially verified`, `not verifiable from submitted PDF`, `rejected`, `deduplicated`, or `disputed`. `91-ai-actionable-ledger.csv` limits `Impact` to `material` or `local`; optional AI findings do not enter this CSV.

`LedgerID` and `ChairFindingID` are unique continuous sequences from `L01` and `C-F01`. `SourceReviewerFindingIDs` is a canonical duplicate-free comma-space list sorted by reviewer number and finding number. Across all `91` rows, every current reviewer `S0`--`S3` finding ID occurs exactly once—neither disappearance nor repeated adjudication is allowed. The chair's `Adjudicated findings` table is an exact field projection of the CSV, including `EvidenceStatus`. Rejected, disputed, and not-verifiable dispositions also appear in the chair's disagreement table. Every disagreement `Source item IDs` token must identify an actual current reviewer question or an actual current `ChairFindingID`; phantom `Rn-Qxx` and phantom `C-Fxx` values are invalid.

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

Every substantive actor runs its exact read-only gate before freezing or exiting:

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

The ordinary reviewer and AI gates do not enumerate the round root or probe peer/downstream files. R4/R5/master's-R3 owner gates open only their exact packet and owned-ledger closure. The Chair gate uses the full validator's explicit `--pre-stage-s` mode: `93`, `94`, and `95` are forbidden, and no diagnostic is waived by message matching. The Stage-S gate opens only the current R/AI/Chair summary sources, `91`/`92`, and S's three outputs; it never opens the PDF, packet, `02`--`04`, helpers, prior artifacts, or `95`. All scoped commands are read-only and create no `95-bundle-validation.md`.

The R4 citation access receipt is closed. `ContentSourceOpened` is exactly one complete source URL. Any redirect, fallback, or failed route that was actually accessed is recorded in `DispositionEvidence` as `accessed endpoint: <URL>` followed only by a semicolon, newline, or field end. Bare URLs in `PublicIdentifier`, attached propositions, locators, or unmarked disposition prose do not prove access. The R4 ledger/report receipt must contain every source and explicitly marked access endpoint once; an unrecorded receipt endpoint or an omitted recorded endpoint fails both scoped and full gates.

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
