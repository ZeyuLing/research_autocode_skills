# Imagegen-Only Figure Protocol

Use the installed `imagegen` skill for every figure asset. This rule covers method overviews, module diagrams, teasers, bar/radar/chart images, qualitative comparisons, case-study layouts, and placeholders. Do not use any other drawing skill or render figures with SVG, TikZ, draw.io, plotting code, HTML, CSS, or canvas.

The registered raster must be the graphical subject, not a provenance token. Inside a LaTeX `figure`, use only placement, centering, `includegraphics`, captions, labels, tracked draft macros, spacing, and ordinary raster `subfigure` environments. The validator rejects every unrecognized residual command or visible TeX body, including display math, text-built diagrams, outer `scalebox`/`resizebox`, `tabular`, `array`, `rule`, `minipage`, boxes, custom macros, and nested inputs. It also rejects author-side redefinition or dynamic construction of `includegraphics`; do not add a tiny registered image or alter raster-command semantics to evade the imagegen-only contract.

LaTeX tables and mathematical equations remain LaTeX, not image assets.

For teasers, overviews, pipelines, and graphical abstracts, also read
[figure-composition.md](figure-composition.md). Its reference-board, claim-first
brief, multi-candidate, targeted-refinement, and independent-critic gates are
mandatory.

## Imagegen execution

1. Load the installed `imagegen` skill and follow its built-in-tool-first policy.
2. Use one imagegen call per distinct figure or variant.
3. Treat a new figure as generation. Treat a revision that must preserve the selected figure as an edit.
4. When editing a local figure through the built-in path, inspect it with `view_image` first.
5. Use CLI fallback only under the conditions and user-confirmation rules defined by `imagegen`.
6. Never leave a project-consumed asset only in the default generated-images directory; move or copy the selected version into the project.

## Figure planning

Derive visual emphasis from the frozen novelty and claim graph. Include only details needed to communicate the problem, the novel mechanism, and the claimed effect.

- Overview: use `scientific-educational` or `infographic-diagram`.
- Complex module: use `scientific-educational`.
- Teaser: use `infographic-diagram`, `scientific-educational`, or `productivity-visual` when results are the selling point.
- Quantitative chart: use `productivity-visual` with exact labels and values.
- Qualitative layout: use `compositing` when real outputs are inputs; use a clearly marked scientific placeholder before results.

Do not render a teaser or overview directly from Method prose. First complete the
reference-board preflight and claim-first figure brief in
`figure-composition.md`. Generate at least six composition directions spanning at
least three composition archetypes, then apply at least three single-change
imagegen refinements to the selected direction.

## Prompt contract

Save each prompt under `figures/prompts/<figure-id>-vN.md` with:

```text
Use case: <imagegen taxonomy slug>
Asset type: publication figure for <venue>; <single-column|double-column|page-width>
Primary request: <one-sentence visual objective>
Figure role: <teaser|overview|pipeline|module|qualitative|chart>
10-second message: <one reviewer takeaway>
Paper claim: <claim and contribution IDs>
Final-size target: <physical width, maximum height, aspect ratio>
Reference synthesis: <reference-board path and transferred principles>
Composition grammar: <panels/zones, alignment grid, dominant spine>
Reading order: <numbered flow and branch semantics>
Novelty emphasis: <focal mechanism and visual-weight device>
Color semantics: <one stable meaning per color and line style>
Text budget: <exact labels, maximum count, maximum words per label>
Hard vetoes: <overlap, crossings, dead corners, dense prose, and figure-specific failures>
Candidate directions evaluated: <integer; at least 6 for teaser/overview>
Targeted refinements completed: <integer; at least 3 for teaser/overview>
Input images: <index and role for every input>
Scene/backdrop: clean paper-compatible background
Subject: <problem, method flow, or comparison>
Style/medium: polished raster scientific infographic
Composition/framing: <landscape/portrait and reading flow>
Domain visual evidence: <at least three semicolon-separated problem-native primitives>
Generic-box area budget: <= 35%
Three-glance hierarchy: <first glance>; <second glance>; <third glance>
Composition archetypes evaluated: <integer; at least 3>
Color palette: low-saturation palette with accessible contrast
Text (verbatim): "<only required terms from terminology.csv>"
Evidence status: <conceptual-placeholder|measured-outputs; required for qualitative figures>
Constraints: emphasize <claim/module IDs>; preserve evidence; readable at final size; no watermark
Avoid: decorative detail, dense prose, unused whitespace, high-saturation clashes, invented modules
```

Quote exact in-image text. Keep labels few and short because raster text is error-prone. Require no extra characters or labels.

Treat every saved prompt as an immutable execution receipt: never rewrite it to
make a later validator pass. A genuinely surgical edit may use a short prompt
that specifies exactly one change and explicitly preserves everything else. In
that case, its full composition contract and critic gates may be inherited only
from the direct input image's prompt and QA, and only when the parent's
provenance hashes bind both that prompt and that exact input raster. Keep the
child prompt, child input path/hash, and parent chain intact. A redesign,
multi-change edit, or unbound input must restate and satisfy the full contract.

## Design principles

- Emphasize novelty, not routine implementation detail.
- Use low saturation while retaining readable contrast and grayscale separation.
- Avoid both large empty blocks and visual overcrowding.
- Let arrows, grouping, shape, and spatial relationships carry meaning; minimize prose.
- Match terminology, capitalization, color mapping, and module order to Method exactly.
- Make the core problem, innovation, and flow clear at a glance; leave fine detail to the caption and paper.
- Prefer one overview. Split into subfigures or a separate module figure only when complexity justifies it.
- Reject a generic card-grid or equal-weight module inventory when the paper has a
  clear focal contribution.
- Inspect teasers and overviews inside the compiled PDF at their intended physical
  width; full-screen readability does not count.

## Evidence preservation

For real qualitative results, label each input image role and require: “change only layout and framing; preserve every model output pixel/content and label association.” Compare generated layouts against the original inputs. Reject any version that alters, beautifies, invents, removes, or swaps observations.

Before measured results exist, do not bake predicted numeric labels into a raster chart. Use an unmistakable no-number imagegen placeholder, and place every predicted value in the caption or adjacent LaTeX table through `\PredResult{<ID>}{...}` with a matching nearby TODO. Regenerate the complete chart through imagegen after measured values arrive.

Every planned qualitative result must already have a generated raster before
`SKETCH_COMPLETE`. A red paragraph that says a figure will be generated later is not
a figure. Set `type=qualitative`, bind `result_ids` to the exact
`\QualPlaceholder` ID, declare `Evidence status: conceptual-placeholder`, and require
the in-image disclosure `CONCEPTUAL PLACEHOLDER - REPLACE WITH RAW OUTPUTS`. The
placeholder may show schematic silhouettes, intended case columns, baseline/method
rows, contact/trajectory diagnostics, and failure-marker legends, but must contain no
fabricated screenshots, scores, or apparent model outputs. Its caption must state that
it is a layout specification rather than experimental evidence.

For conceptual qualitative placeholders, the QA note must include `Evidence status:
conceptual-placeholder` plus `Placeholder disclosure: pass`, `No measured-result
simulation: pass`, and `Planned comparison fidelity: pass`. For measured qualitative
figures, it must instead state `Evidence status: measured-outputs`, `Input evidence
preservation: pass`, and `Baseline-output association: pass`.

## Artifact and QA contract

Capture the raw imagegen dispatch receipt under figures/qa/. It records the
imagegen skill/tool identity, call ID, prompt/output hashes, and timezone-aware
start/completion timestamps. For a user-approved imagegen CLI fallback, use
tool=imagegen.cli and additionally record user_confirmed=true, the confirmation
ID, and command hash.

Copy the invoked imagegen SKILL.md into figures/qa/, hash it, and bind the same
skill hash in both the provenance record and dispatch receipt.

Final paper assets must be valid PNG rasters at least 128 by 128 pixels. Copy
every edit/reference input into the project and list semicolon-separated
project-relative paths in input_paths. Use vN in version; link every figure to
at least one claim, and link overview/module figures to their module IDs.

Begin every passing QA note with the exact line "QA status: pass"; otherwise the figure remains unapproved.

Record every selected figure in `figures/manifest.csv`:

```text
figure_id,type,claim_ids,module_ids,result_ids,backend,mode,prompt_path,
input_paths,generated_path,paper_path,version,status,qa_path,provenance_path,
output_sha256
```

Every populated row must set `backend=imagegen`; no other value is valid.

For every selected asset, save `provenance_path` as JSON containing:

```json
{
  "skill_name": "imagegen",
  "tool": "image_gen.imagegen",
  "mode": "generate",
  "generated_at": "timezone-aware ISO timestamp",
  "prompt_sha256": "...",
  "output_sha256": "...",
  "receipt_path": "figures/qa/<figure-id>-receipt.json",
  "receipt_sha256": "...",
  "skill_snapshot_path": "figures/qa/imagegen-SKILL.md",
  "skill_snapshot_sha256": "..."
}
```

Set the manifest `output_sha256` to the same digest. The digest must match both
`generated_path` and the unmodified paper copy at `paper_path`. Every
`\includegraphics` target must have exactly one manifest row and provenance
record; do not register an unused selected/final asset.

Save final raster images under `figures/generated/` and paper-consumed copies under `paper/figures/`. Save a QA note under `figures/qa/` covering:

- exact text and terminology;
- arrows and flow direction;
- scientific/content accuracy;
- result values and label associations;
- no hallucinated modules or evidence;
- no watermark;
- color and contrast;
- readability at actual single/double-column size;
- consistency with caption and Method.

For teasers and overviews, the QA note must additionally contain the exact
pass/fail headings defined in `figure-composition.md`: Faithfulness, Conciseness,
Readability, Aesthetics, Domain evidence, Non-generic composition, Three-glance
hierarchy, Novelty salience, Rectangular efficiency, and Final-size inspection.
Any failure blocks selection.

Iterate with one targeted imagegen edit at a time and repeat critical invariants on every edit.

Before PaperJury, freeze a path-resolvable figure evidence bundle inside the review
snapshot. Copy the complete `figures/` tree (manifest, prompts, selected and input
images, candidates, QA notes, receipts, provenance, skill snapshot, and reference
boards) plus every paper-consumed file under `paper/figures/`. Preserve project-relative
paths so every manifest path resolves from the frozen snapshot; a final PNG without its
prompt/input/receipt chain is not reviewable evidence.
