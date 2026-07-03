---
name: latex-float-layout
description: Rebalance figures and tables in LaTeX papers when floats pile up on late pages, tables appear mid-page or at the bottom, or multiple two-column floats crowd a single page. Use for academic manuscripts, IEEE/CVF/ACM-style two-column papers, Overleaf merges, and camera-ready layout passes where float placement must be adjusted without changing the scientific content.
---

# LaTeX Float Layout

## Overview

Use this skill to redistribute LaTeX paper figures and tables by inspecting the compiled PDF, editing float placement and source order, and verifying the final page-by-page layout visually.

The goal is not to force every float to its first source position. The goal is a readable paper where tables are top-aligned, figures and tables are spread across pages, and wide floats do not accumulate near the end.

## Workflow

1. Read the venue constraints first. Treat main-body page limits, appendix/reference exclusions, and mandatory float placement rules as hard constraints.
2. Compile the paper at least twice before judging layout.
3. Locate the page where appendix and references begin from the PDF/log. Do not optimize figure/table balance if it pushes the main body over the venue limit.
4. Generate a whole-paper contact sheet from the PDF. Prefer `scripts/make_pdf_contact_sheet.py` when Ghostscript and Pillow are available.
5. Map each float to its PDF page with `main.aux` labels:

```bash
rg -n "newlabel\\{(tab|fig):" main.aux
```

6. Inventory float sources with:

```bash
rg -n "\\\\begin\\{(figure|table)\\*?\\}|\\\\input\\{.*(fig|tab)" .
```

7. Apply the smallest set of source-order, placement, and float-parameter changes that fixes the visible imbalance without violating the page budget.
8. Recompile twice and regenerate the contact sheet. Keep iterating until the PDF content, not just the LaTeX source, satisfies both page-count and layout rules.

## Layout Rules

- Page budget comes first. If the venue limits the main paper to 10 pages excluding appendix/references, the appendix must begin after page 10 at the latest.
- Keep tables at the top of pages. This applies to both `table` and `table*`.
- Avoid placing more than one major two-column float on the same page when a nearby text page can absorb one of them.
- If a page must contain multiple floats, prefer one table at the top plus one figure lower on the page over stacked tables in the middle or bottom.
- If several single-column tables or figures must share a page, aim for left/right column balance rather than stacking them all in one column.
- Do not let floats collect on the last pages. Move qualitative figures and secondary tables earlier or later by source order, but keep them near the section that discusses them.
- When page budget is tight, move illustrative qualitative figures or detailed protocol material to the appendix before moving core numeric result tables.
- Avoid large blank float pages. A page with only one small float is usually worse than a page with two related floats and explanatory text.
- Preserve reading logic: do not move a float so far from its first reference that the reader loses context.

## Preferred Fixes

Start with semantic source-order changes:

- Move a figure from an unrelated earlier subsection into the subsection that discusses it.
- Put a section's table before a qualitative figure if the table must be top-aligned.
- Move explanatory text before a large table when that text can fill the preceding page and the table can land at the next page top.

Then use placement controls:

- Use `[t]` for two-column tables that should obey global float limits.
- Use `[b]` for qualitative two-column figures when they would otherwise push a table away from the top. This requires a class/package setup that supports bottom double-column floats, such as `stfloats`.
- Use `[!t]` sparingly. It can override useful global constraints and cause float pileups.
- Keep single-column tables as `[!t]` or `[t]` when they naturally distribute across left and right columns.

Then tune global float behavior in the preamble when the pattern is systematic:

```tex
\setcounter{dbltopnumber}{1}
\makeatletter
\setlength{\@dblfptop}{0pt}
\setlength{\@dblfpsep}{8pt plus 1fil}
\setlength{\@dblfpbot}{0pt plus 1fil}
\makeatother
```

This limits ordinary top double-column float stacking and makes double-column float pages top-aligned instead of vertically centered.

Use page/column breaks last:

- `\newpage` can be useful in two-column papers because it may move to the next column without flushing all floats.
- `\clearpage` is stronger and often creates sparse pages. Use it only at major result-section boundaries after checking the PDF.
- Avoid scattering many manual breaks. If more than two or three are needed, revisit float order and placement specs first.

## Verification Checklist

- The main body page count satisfies the venue rule, with appendix and references excluded exactly as the venue defines them.
- Tables appear at page tops or at the top of float pages.
- No late-page cluster of several floats remains.
- No page is dominated by a small isolated table or figure with large blank space.
- At most one major two-column table/figure appears on most pages; exceptions are deliberate and visually acceptable.
- Single-column floats sharing a page are split across columns when possible.
- Captions, labels, references, and table numbering remain correct after two LaTeX runs.

## Helper Script

Create a contact sheet for visual review:

```bash
python3 scripts/make_pdf_contact_sheet.py main.pdf --out /tmp/paper-contact.png
```

Open the generated PNG and judge the actual page distribution before making more edits.
