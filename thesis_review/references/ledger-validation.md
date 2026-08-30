# Machine-readable ledger and bundle validation

Use these contracts for every complete review round. Markdown reports contain reasoning and signed dispositions; CSV files are the authoritative row sets for completeness, deterministic IDs, and reconciliation. Mechanical validation never replaces reviewer judgment.

## 1. CSV conventions

- UTF-8 with a header row and RFC-4180-style quoting for commas, quotes, or newlines.
- Stable, case-sensitive IDs assigned in frozen-PDF reading order: pages are
  `P0001...`; rendered bibliography entries are `REF0001...`; citation
  occurrences are `C0001...`; and sources within an occurrence are
  `C0001-S01...`. Each sequence is continuous with no gaps.
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

The validator independently derives the bibliography's contiguous physical-page span from the unique **longest** rendered line-start entry run `[1]...[N]`, requires its length to equal the bibliography inventory, and requires a rendered `References`/`参考文献` heading on the run's first page; a free-text `Region` value or an isolated body `[1]` cannot remove an arbitrary body page from extraction. It then re-extracts every balanced square-bracket span containing at least one digit from every non-bibliography physical page of the frozen PDF with the bundled `pypdf` text extractor; spans may cross extracted line breaks and have no silent length cutoff. The candidate ledger must contain exactly that ordered sequence: continuous `BC0001...` IDs, the exact physical page, a whitespace/dash-normalized marker, the exact ordered integer list after expanding one-to-four-digit pure-integer ranges while preserving duplicates (or `N/A` for decimal/mixed/formula spans), the validator's deterministic normalized 160-character context window on both sides, and the frozen-PDF hash. `Classification` is exactly `citation` or `non-citation`; `ClassificationEvidence` must identify the local grammatical role rather than merely say “checked.” A citation row must be a pure-integer citation marker, maps to exactly one continuous `Cnnnn` occurrence, and its expanded numbers must equal that occurrence's ordered `DisplayedReferenceID` sequence. A non-citation row uses `MappedOccurrenceID=N/A` and has no citation-inventory occurrence. Decimal/mixed/formula spans, zero-bearing markers, duplicate-number vectors, and markers used immediately as mathematical set/interval membership or explicitly introduced as an array/vector/quantization-level list cannot be classified as citations. Every citation occurrence maps back to exactly one candidate; every inventory Pair row has the same physical page and exact deterministic normalized context as that candidate.

Every unmatched `[` or `]` on a non-bibliography page receives one continuous `UBG0001...` row in `00-unmatched-bracket-ledger.csv`. The physical page, glyph, and deterministic normalized context must equal the validator extraction; the disposition must explain the visible role and cannot claim that none were found. A positive manifest count must equal this row count and name the sidecar; only a zero count permits an explicit none-found disposition. Any candidate or unmatched-glyph omission, extra row, reordering, page/marker/context mismatch, classification/mapping mismatch, or obvious mathematical false positive invalidates Stage P.

The Stage-P citation inventory is mechanical after candidate disambiguation. `PDFLocation` must name the candidate's valid physical page, and `AdjacentPDFText` must copy the candidate's deterministic normalized extraction window exactly; it is an anchor, not a semantic proposition verdict.

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

The Pair-ID set must exactly equal `00-citation-inventory.csv`. `Support` is one of `direct`, `partial`, `context-only`, `mismatch`, `unverifiable`, or `not-needed`, and `MetadataStatus` is one of `verified`, `mismatch`, or `unverifiable`. A substantive support verdict other than `unverifiable` requires an `http(s)` content endpoint in `ContentSourceOpened` and a structured locator such as `page 14`, `section 3.2`, `Table 2`, `Figure 4`, `Equation 7`, `Abstract`, or `publisher record: DOI ...`; a bare word such as `section` is invalid. Publication metadata alone is acceptable only when the attached proposition is publication metadata. The Markdown projection uses the exact twelve headers in `citation-audit.md`, sorts by `PairID`, and compares every projected field. `Displayed label` is the exact `00-bibliography-inventory.csv` label for `ReferenceID`. `Content source opened and exact locator` is compact JSON with exact key order `{"content_source_opened":"<ContentSourceOpened>","exact_source_locator":"<ExactSourceLocator>"}`; all other non-hash CSV fields map one-to-one to their named Markdown column. Every CSV PairID must occur exactly once as a complete table cell.

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

## 3. Validation command

Before a doctoral R5 freezes its report and owned ledgers or exits, run the scoped validator repeatedly against the exact current bundle root:

```text
python rules/scripts/validate_r5_output.py <exact-round-root>
```

R5 passes this gate only when the command exits `0` and its first nonempty stdout line is exactly `PASS`. Do not skip, patch, mock, replace, or suppress either `validate_r5_output.py` or its sibling `validate_review_bundle.py`. When the failure is confined to R5-owned output, correct only the current R5 report, `02`, `03`, authorized renders, or the declarations inside those R5-owned Markdown files and rerun until PASS. R5 must not edit the Stage-P packet, process envelope, frozen PDF, staged rules, or any other input. If the scoped validator identifies a packet or frozen-input defect, stop and report failure to Stage O; Stage O invalidates the dependent clean-room chain and performs the required clean Stage-P/downstream retry. The scoped command is read-only, does not create `95-bundle-validation.md`, does not require or open R1--R4/AI/Chair/Stage-S/Stage-V artifacts, and does not enumerate the bundle root to discover peer outputs. It is mechanical rule infrastructure only: validator output and source code are never thesis/citation evidence or a source of findings, and PASS never replaces manual semantic and visual sign-off.

Run the validator after Stage S in an environment with `pypdf` and Pillow available (the bundled Codex workspace Python includes both; with `uv`, use `uv run --with pypdf --with pillow`):

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
