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
- Process large ledgers in deterministic ID ranges and checkpoint batches; concatenate only after duplicate/missing/extra validation.
- Every sidecar records the frozen PDF SHA-256 in its companion Markdown report and, when practical, in a `PDFSHA256` column.

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

The Page-ID set must exactly equal `00-page-inventory.csv`; `PhysicalPage` must form `1..N` with no gaps or duplicates; and `Pnnnn` must map to physical page `nnnn` in both inventories. Every suspect page uses `full-scale`; every page has a non-empty disposition and inspection mode. `RenderDPI` normally follows the 160--200 dpi audit target; the validator accepts 120--600 only as a mechanical sanity range. Retain one decodable PNG as `page-renders/<PageID>.png`; its dimensions must match the frozen PDF page at the declared DPI, and `RenderArtifactIDHash` is that file's exact 64-hex SHA-256, optionally prefixed by the matching PageID. Each Markdown master must contain exactly one complete pipe table with its documented ID header, an immediately following separator row, consistent column counts, and every corresponding CSV ID exactly once in that table's ID column. Ledger IDs must not recur in prose, code fences, another column, or another table; prose mentions and standalone pipe rows do not count as ledger rows and invalidate the projection.

### Bibliography audit

- `03-bibliography-audit-ledger.csv`: `ReferenceID,DisplayedLabel,Cited,Field,RenderedValue,CanonicalValue,Verdict,EvidenceEndpoint,EndpointType,CheckedAt,EvidenceNote,FindingDisposition,PDFSHA256`

For each `ReferenceID`, the `(ReferenceID,Field)` key is unique and the mandatory field set is exactly:

`type,title,ordered_authors,year,venue,publication_status,volume,issue,pages_or_article_number,doi,arxiv_id,arxiv_version,url,access_date,isbn_or_other_persistent_id,existence,retraction_withdrawal_correction_superseding`.

`Verdict` is one of `exact`, `mismatch`, `legitimate N/A`, or `unverifiable`. A non-`unverifiable` row records an `http(s)` authoritative endpoint. `CheckedAt` is an ISO-8601 date or datetime. For `unverifiable`, `EvidenceNote` records the attempted official route/query/date and negative/access result when no authoritative endpoint exists, in which case `EvidenceEndpoint` may be blank. The Markdown projection must contain every CSV ReferenceID exactly once as a complete table cell.

### Citation-claim audit

- `04-citation-claim-audit-ledger.csv`: `PairID,OccurrenceID,PDFLocation,ExactAttachedProposition,ReferenceID,PublicIdentifier,ContentSourceOpened,ExactSourceLocator,Support,MetadataStatus,SeverityFinding,DispositionEvidence,PDFSHA256`

The Pair-ID set must exactly equal `00-citation-inventory.csv`. `Support` is one of `direct`, `partial`, `context-only`, `mismatch`, `unverifiable`, or `not-needed`. A substantive support verdict other than `unverifiable` requires an `http(s)` content endpoint in `ContentSourceOpened` and a structured locator such as `page 14`, `section 3.2`, `Table 2`, `Figure 4`, `Equation 7`, `Abstract`, or `publisher record: DOI ...`; a bare word such as `section` is invalid. Publication metadata alone is acceptable only when the attached proposition is publication metadata. The Markdown projection must contain every CSV PairID exactly once as a complete table cell.

### Chair and summary reconciliation

- `91-revision-ledger.csv`: `LedgerID,Priority,ChairFindingID,SourceReviewerFindingIDs,Severity,Remedy,ExactPDFAnchor,DirectObservation,MinimumEditEvidence,Dependency,Owner,Status,Verification`
- `91-ai-actionable-ledger.csv`: `AIFindingID,Impact,ExactPDFAnchor,DirectStyleObservation,MinimumEditingAction,Status,Verification`
- `93-current-actionable-items.csv`: `LedgerID,CurrentFindingIDs,SeverityRemedy,ExactPDFAnchor,DirectPDFObservation,MinimumRequiredAction,OriginReviewers,ChairDisposition`
- `93-current-ai-actionable-items.csv`: `AIFindingID,Impact,ExactPDFAnchor,DirectStyleObservation,MinimumEditingAction,ChairStatus`

The open required academic `LedgerID` set in `91-revision-ledger.csv` must exactly equal the `LedgerID` set in `93-current-actionable-items.csv`. The open `material`/`local` `AIFindingID` set in `91-ai-actionable-ledger.csv` must exactly equal the ID set in `93-current-ai-actionable-items.csv`. Duplicates, missing IDs, or extra IDs invalidate Stage S.

The matching rows must also agree field by field. Academic mapping: `CurrentFindingIDs = ChairFindingID`; `SeverityRemedy = Severity + "/" + Remedy`; `ExactPDFAnchor = ExactPDFAnchor`; `DirectPDFObservation = DirectObservation`; `MinimumRequiredAction = MinimumEditEvidence`; `OriginReviewers = SourceReviewerFindingIDs`; `ChairDisposition = Status`. AI mapping: the two files use identical `AIFindingID`, `Impact`, `ExactPDFAnchor`, `DirectStyleObservation`, and `MinimumEditingAction`, with `ChairStatus = Status`. Any same-ID content drift invalidates Stage S.

Current-round academic and AI ledger `Status` values are limited to `open`, `closed`, `resolved`, `not required`, `not applicable`, or `N/A`; any other value is invalid. `91-revision-ledger.csv` additionally limits `Priority` to `P0`--`P3`, `Severity` to `S0`--`S3`, and `Remedy` to `W/E/N/P`. `91-ai-actionable-ledger.csv` limits `Impact` to `material` or `local`; optional AI findings do not enter this CSV.

### Optional helper provenance

Every consumed helper writes `helpers/Hxx-provenance.json` with exactly these top-level fields:

`actor_id,round_id,retry_id,prompt_sha256,fresh_context_declaration,input_receipt_access_declaration,received_blocks,opened_inputs,tool,version,command_or_query,pdf_sha256_start,pdf_sha256_end,outputs,limitations,recipient_stages`

`received_blocks`, `opened_inputs`, `limitations`, and `recipient_stages` are arrays. `outputs` is a non-empty array of objects with exactly `file` and `sha256`; `file` is a neutral basename inside `helpers/`, and its hash is verified. The prompt and PDF hashes are 64 hexadecimal characters; both PDF hashes equal the frozen PDF. Every non-provenance file in `helpers/` must be registered by exactly one provenance record. Unregistered, multiply registered, missing, path-traversing, or hash-mismatched helper output invalidates the bundle. If no helper is consumed, omit the `helpers/` directory.

## 3. Validation command

Run the validator after Stage S in an environment with `pypdf` and Pillow available (the bundled Codex workspace Python includes both; with `uv`, use `uv run --with pypdf --with pillow`):

```text
python scripts/validate_review_bundle.py <round-directory> --write-report <round-directory>/95-bundle-validation.md
```

The validator parses the frozen PDF and checks its real physical-page count; independently binds the rendered bibliography span; re-extracts numeric-bracket candidates and unmatched glyphs; checks required files by degree type, deterministic ID sequences, exact candidate page/context joins, complete Markdown schemas and CSV ID projections, render-record sanity, mandatory bibliography fields and endpoint/date shape, citation content-endpoint/locator shape, allowed verdict/status values, page coverage, current academic/AI action reconciliation, complete Stage-S conclusions/current-only identity, chair citation counts/gate consistency, and required clean-room declarations. A nonzero exit code blocks a claim of completion. Review the printed failures; do not edit ledgers mechanically merely to satisfy counts.

## 4. Manual sign-off that validation cannot replace

The owning reviewer still signs:

- every page's actual visual disposition;
- every bibliography field's canonical value and evidence quality;
- every citation pair's exact attached proposition and source-content support;
- every finding's severity/remedy and grade consequence;
- every AI-style finding's contextual recurrence and impact;
- the chair's cross-ledger identity/support adjudication.

Counts, live URLs, hashes, and `pending=0` never establish semantic correctness by themselves.
