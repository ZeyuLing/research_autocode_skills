# Rendered pagination and float audit

Use this protocol for every initial review, direct-edit round, and independent re-review. The objective is to make “all pages inspected” reproducible and to detect layout failures caused by interactions among floats, forced placement, captions, headings, and page breaks.

## 1. Freeze and render

1. Record PDF path, SHA-256, build time, physical page count, and the mapping between physical and printed/logical page numbers.
2. Render every physical page at 160--200 dpi or another resolution that keeps body text, figure labels, and table notes legible.
3. Build a whole-document contact sheet for density triage. Do not use the contact sheet as the only visual inspection.
4. Inspect each page individually or in groups small enough to read the page structure. Open every suspect page at full-page scale and zoom embedded figure/table text when necessary.

## 2. Create the mandatory page ledger

Write `02-page-layout-ledger.md` with one row per physical page:

| Physical page | Printed page | Region | Dominant content | Signals | Full-scale checked | Disposition | Evidence |
|---|---|---|---|---|---|---|---|

`Region` distinguishes front matter, chapter, references, appendix, and back matter. `Signals` records automated or visual triage. `Disposition` is `clean`, `intentional`, `finding <ID>`, or `recheck after edit`. Do not omit blank pages; explain whether each is template-mandated, chapter-structure-induced, or erroneous.

## 3. Mandatory triage signals

Treat these as prompts for full-scale inspection, not automatic defects:

- less than roughly 55 percent of the usable text area occupied on an ordinary content page;
- more than roughly 70 percent of the usable area occupied by one float with little explanatory prose;
- an isolated heading, caption, one-line paragraph, bibliography orphan, or table continuation;
- two or more figures/tables placed consecutively without explanatory text when the source contains prose that could separate them;
- large unexplained bottom whitespace, especially immediately before a figure/table on the next page;
- a float-only or nearly float-only page that is not justified by an unavoidable full-page artifact;
- abrupt page-count or label-location changes after a local edit;
- a figure, table, caption, equation, or embedded label touching or crossing the text block, header, footer, or crop boundary;
- neighboring pages with conspicuously inconsistent artifact widths or text scale.

Natural chapter-end whitespace, intentionally blank verso pages, and required front-matter separations are not findings when verified against the template.

Visual estimation against the ordinary text block is sufficient for triage; exact pixel-area measurement is optional. The approximate thresholds exist to force inspection, not to manufacture numerical pass/fail rules.

## 4. Source forcing audit

Search the complete active source tree for at least:

```text
[H]
\FloatBarrier
\clearpage
\newpage
\pagebreak
\afterpage
\ContinuedFloat
```

For every active occurrence:

1. identify the nearest section, figure/table label, and rendered physical page;
2. inspect at least pages `p-1`, `p`, and `p+1` at full scale; use `p-2` and `p+2` for tall artifacts or float queues;
3. determine whether the construct is required by semantics/template or merely compensates for an earlier layout problem;
4. check whether it prevents later prose from filling the remaining page, creates a float stack, separates a heading from its paragraph, or moves a small artifact onto a wasteful page;
5. record the result in the page ledger even when clean.

An `[H]` artifact that cannot fit in the remaining space and therefore leaves abnormal whitespace before moving to the next page is a pagination defect. Removing `[H]` blindly is not a sufficient repair; inspect the resulting float order and neighboring pages.

If the review target is a frozen PDF and active source is not supplied, complete the rendered-page ledger and report visible pagination findings normally. Record the forcing audit as `not verifiable--source not supplied`, do not attribute the symptom to a specific LaTeX construct, and make source inspection a verification step. The bounded PDF-only review may still be complete, but its source-level cause and repair validation remain explicit limitations.

## 5. Figure and table continuation gate

For a cropped, split, rotated, or continued artifact:

1. render the uncropped source and both/all final parts at legible scale;
2. verify that the union of final parts covers every semantic element exactly once, allowing only harmless background overlap;
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
6. mark the prior finding resolved only after the final PDF, not the LaTeX source, visibly satisfies the remedy.

The gate passes only when every physical page has a ledger row, every signal has a disposition, every forcing construct has a neighbor-page audit, and no unresolved actionable pagination finding remains.
