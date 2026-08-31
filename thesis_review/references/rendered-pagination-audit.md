# Rendered pagination and float audit

Use this protocol for every initial review and independent re-review of the frozen PDF, and for rendered validation after a direct-edit task. In blind review, the page-ledger owner also follows the fresh-context and exact-input requirements in `clean-room-orchestration.md`; prior page ledgers, conversation hints, source-level diagnoses, and old PDF versions are not triage inputs. The objective is to make “all pages inspected” reproducible and to detect visible layout failures involving figures, tables, captions, headings, and page breaks. Blind reviewers do not inspect or infer the underlying source constructs.

## 1. Freeze and render

1. Record neutral PDF path, SHA-256, freeze time, physical page count, and the mapping between physical and printed/logical page numbers. Record PDF metadata creation time separately as untrusted metadata; real build time is `not available from the PDF` unless a permitted governing record supplies it.
2. Render every physical page at 160--200 dpi or another resolution that keeps body text, figure labels, and table notes legible.
3. Build a whole-document contact sheet for density triage. Do not use the contact sheet as the only visual inspection.
4. Inspect each page individually or in groups small enough to read the page structure. Open every suspect page at full-page scale and zoom embedded figure/table text when necessary.

## 2. Create the mandatory page ledger

Write `02-page-layout-ledger.csv` as the machine-readable master and mirror it in `02-page-layout-ledger.md`, with one row per physical page:

| Page ID | Physical page | Printed page | Region | Dominant content | Signals | Inspection mode/scale | Render DPI | Render artifact ID/hash | Neighbor pages checked | Disposition | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|

This is an exact projection of `02-page-layout-ledger.csv`, not an independently
worded summary. Use the header above verbatim and in that order. Sort rows by
`PageID`, then project these CSV fields in order:
`PageID,PhysicalPage,PrintedPage,Region,DominantContent,Signals,InspectionModeScale,RenderDPI,RenderArtifactIDHash,NeighborPagesChecked,Disposition,Evidence`.
Every logical Markdown cell must equal the corresponding authoritative CSV
scalar under the common escaping rule in `ledger-validation.md`; the
`PDFSHA256` column is projected through the checksum declaration and is checked
separately on every CSV row. Changing a disposition, evidence statement, render
hash, or any other non-ID cell while retaining the same Page ID invalidates the
projection.

Use continuous deterministic Page IDs `P0001...` in physical-page order, with `Pnnnn` bound to physical page `nnnn`. Retain every inspected PNG in the round as `page-renders/<PageID>.png`; the validator decodes its pixels and checks its PNG structure, pixel dimensions against the corresponding PDF page and declared DPI, and exact SHA-256. `Region` distinguishes front matter, chapter, references, appendix, and back matter. `Signals` records automated or visual triage. `Inspection mode/scale` is `individual`, `small-legible-group`, or `full-scale` with the actual zoom/scale; every page needs one valid inspection record, and every suspect page needs `full-scale`. `Render artifact ID/hash` records the retained PNG's exact 64-hex hash, optionally prefixed by its PageID; do not put an arbitrary token or the source-PDF hash there. `Disposition` is `clean`, `intentional`, `finding <ID>`, or `recheck after edit`. Do not omit blank pages; explain whether each is template-mandated, chapter-structure-induced, or erroneous. Reconcile the parsed PDF page count, retained render filenames, Stage-P inventory, CSV, and complete Markdown table Page-ID sets; duplicate/missing/extra IDs and PageID/physical-page swaps must all be zero.

The ledger is page-specific evidence, not 172 copies of a completion phrase.
Carry the current page's Stage-P `MechanicalSignals` into `Signals` or
`Evidence`, describe the actual dominant page content (for example the figure,
table, equation block, heading transition, bibliography block, or prose/float
combination) rather than repeating `Region`, and record the concrete visual
condition inspected. A standardized checklist may be part of `Evidence`, but
it cannot be the entire evidence cell on nearly every page. An `intentional`
blank/separator page additionally states the structural reason it is expected.
Whole-thesis template filling with one identical signal/evidence sentence is an
invalid audit even when every PNG and hash is genuine.

`Neighbor pages checked` records the adjacent or continuation pages actually
examined. It may name current-round PageIDs such as `P0070; P0072` or use
physical-page locators; `Evidence` may likewise use an existing PageID when a
visual conclusion explicitly depends on another rendered page. These are
foreign-key references, not extra primary-key rows: every `Pnnnn` token in
either column must exist in `00-page-inventory.csv`. An unknown PageID, or a
PageID in any other non-ID column or surrounding prose, is invalid. After the
authoritative CSV is complete, run the owner materializer specified in
`ledger-validation.md`; it produces the exact escaped Markdown table and does
not change a page disposition or inspection record.

## 3. Mandatory triage signals

Treat these as prompts for full-scale inspection, not automatic defects:

- less than roughly 55 percent of the usable text area occupied on an ordinary content page;
- more than roughly 70 percent of the usable area occupied by one float with little explanatory prose;
- an isolated heading, caption, one-line paragraph, bibliography orphan, or table continuation;
- two or more figures/tables placed consecutively without visible explanatory text;
- large unexplained bottom whitespace, especially immediately before a figure/table on the next page;
- a float-only or nearly float-only page that is not justified by an unavoidable full-page artifact;
- abrupt page-count or label-location changes after a local edit;
- a figure, table, caption, equation, or embedded label touching or crossing the text block, header, footer, or crop boundary;
- neighboring pages with conspicuously inconsistent artifact widths or text scale.

Natural chapter-end whitespace, intentionally blank verso pages, and required front-matter separations are not findings when verified against the template.

Visual estimation against the ordinary text block is sufficient for triage; exact pixel-area measurement is optional. The approximate thresholds exist to force inspection, not to manufacture numerical pass/fail rules.

## 4. PDF-only pagination-cause boundary

Inspect every visible pagination symptom in the PDF, including abnormal whitespace, float-only pages, detached captions, isolated headings, and figures or tables that appear farther from their discussion than necessary. Inspect at least pages `p-1`, `p`, and `p+1` around each signal; use `p-2` and `p+2` for tall artifacts or apparent float queues.

Do not open the LaTeX/DOCX source or search for `[H]`, `\FloatBarrier`, `\clearpage`, `\newpage`, `\pagebreak`, `\afterpage`, or `\ContinuedFloat` during blind review. A visible symptom may be reported, but its source-level cause must be recorded as `not verifiable from the PDF`. Do not claim that a specific forcing command caused the defect.

During a separately requested direct-edit task, the editor may diagnose and change source constructs. That work is not reviewer evidence. The subsequent independent re-review starts again from the newly frozen PDF and judges only the visible result.

## 5. Figure and table continuation gate

For a cropped, split, rotated, or continued artifact visible in the PDF:

1. render every visible final part at legible scale;
2. verify from the rendered parts that numbering, seams, labels, rows, and semantic units appear continuous and nonduplicated; if completeness requires an unavailable source, mark it `not verifiable from the PDF` rather than guessing;
3. ensure the seam does not cross text, a person/object, plot marks, arrows, table rows, or a motion sequence;
4. retain correct numbering, references, list-of-figures/tables behavior, and an explicit continuation title when required;
5. inspect the page before the first part, every continuation page, and the first page after the artifact.

Do not trade a blank-page defect for unreadably small embedded text. Prefer semantic continuation, reordered explanatory prose, or an aspect-ratio-aware layout over indiscriminate scaling.

## 6. Post-edit regression gate

After any layout-affecting edit:

1. rebuild until references, lists, and float positions are stable;
2. check the log for fatal errors, unresolved references/citations, overflow, and unexpected float warnings;
3. compare total page count and affected figure/table/section page numbers with the previous frozen artifact;
4. render and inspect at least two physical pages before and after every changed location;
5. regenerate the whole-document contact sheet and page ledger, then inspect all new or changed signals at full scale;
6. mark the prior finding resolved only after the final PDF visibly satisfies the remedy.

The gate passes only when `unchecked pages = 0`, every physical page has exactly one deterministic ledger row with a valid inspection mode/scale and render provenance, every visible signal has a disposition, duplicate/missing/extra Page IDs are zero, and no unresolved actionable pagination finding remains. Source-forcing coverage is not part of a PDF-only blind-review gate.
