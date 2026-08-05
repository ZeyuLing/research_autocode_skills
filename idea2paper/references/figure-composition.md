# Teaser and Pipeline Composition

Use this reference for every teaser, overview, pipeline, or graphical abstract. It
turns figure generation into a reference-driven design-and-critique loop while
preserving the imagegen-only rendering contract.

## Research basis

The workflow distills complementary practices from public academic-figure
projects:

- [Google Research PaperVizAgent](https://github.com/google-research/papervizagent)
  retrieves relevant human figures, separates planning from styling, and critiques
  faithfulness, conciseness, readability, and aesthetics.
- [SNL-UCSB paper-writing-skill](https://github.com/SNL-UCSB/paper-writing-skill)
  requires a claim-bound figure spec with components, connections, groupings,
  layout, emphasis, size, and caption before rendering.
- [research-paper-figure-skill-factory](https://github.com/c-narcissus/research-paper-figure-skill-factory)
  distinguishes the 10-second message from 60-second understanding, treats paper
  slot and panel choreography as first-class choices, and compares diverse
  directions before local refinement.
- [visio-scientific-figures](https://github.com/ywq177995212697-droid/visio-scientific-figures)
  checks final paper width, label/connector collisions, line-weight consistency,
  semantic colors, and explicit hierarchy.
- [engineering-figure-agent](https://github.com/heyu-233/engineering-figure-agent)
  uses a claim-centered figure brief and consistent semantic palettes rather than
  decorative color.
- [PaperBanana](https://github.com/dwzhu-pku/PaperBanana) uses a Retriever ->
  Planner -> Stylist -> Visualizer -> Critic loop, supports broad candidate fan-out,
  and makes reference-conditioned multi-round critique part of generation rather
  than a final cosmetic check.
- [AutoFigure](https://github.com/ResearAI/AutoFigure) reinforces a generate ->
  evaluate -> refine loop and treats editable structure and semantic review as
  first-class outputs.

These repositories are design references, not alternate renderers. Every target
paper candidate and revision must still be generated or edited with `imagegen`.

## Reference-board preflight

Before prompting imagegen:

1. Collect 6--10 figures from accepted papers at the target venue or another
   conference in the user's top-venue pool. Prefer official proceedings, author
   project pages, and official GitHub repositories.
2. Include at least three examples with the same figure role and at least two
   examples from an adjacent domain whose visual grammar transfers well.
3. Record paper, venue/year, figure number, source URL, paper slot, reading order,
   density, color semantics, novelty-emphasis device, and one failure to avoid.
4. Extract transferable principles only. Do not reproduce a distinctive layout,
   icon set, or artwork closely enough to imply copying.
5. Select no more than three reference images as imagegen inputs. State each
   image's role: layout reference, hierarchy reference, or palette reference.

Save the synthesis under `figures/qa/<figure-id>-reference-board.md`. The final
prompt's `Reference synthesis:` line must summarize it.

## Claim-first figure brief

Freeze this brief before image generation:

```text
Figure role: teaser | overview | pipeline | graphical abstract
10-second message: one sentence a reviewer should retain
Paper claim: exact claim/contribution IDs served
Paper slot: title block | introduction | method | results
Final-size target: physical width, maximum height, and aspect ratio
Reference synthesis: sources and transferred principles
Composition grammar: panels/zones, alignment grid, and dominant visual spine
Reading order: numbered sequence and branch semantics
Novelty emphasis: focal component and how it receives the most visual weight
Color semantics: one stable meaning per color and line style
Text budget: exact labels, maximum label count, and maximum words per label
Domain visual evidence: at least three domain objects/traces that carry meaning
Generic-box area budget: percentage of canvas occupied by ordinary module boxes
Three-glance hierarchy: first, second, and third visual discoveries
Composition archetypes evaluated: number of genuinely different visual grammars
Hard vetoes: figure-specific rejection conditions
```

Do not style before the thesis, role, and layout grammar are fixed. The core
novelty should be the first or second visual fixation and should receive a clear
size, saturation, border, or position advantage. Routine encoders, datasets, and
losses are scaffolding.

## Teaser grammar

A teaser sells one result or insight; it is not a compressed Method figure.

- Use one dominant contrast or transformation. Common grammars are
  `problem -> key mechanism -> consequence`, paired `existing vs. ours`, or one
  qualitative scene with a surgical callout.
- Limit the figure to two or three visual beats. Keep supporting detail below the
  level needed to reimplement the method.
- Make the proposed insight occupy the visual center or the largest coherent
  region. Do not make baseline and proposed method look equally important.
- Use at most 6--8 short labels in ordinary cases. A label should normally be a
  noun phrase of at most four words; full caption prose never belongs in pixels.
- A reviewer should recover the selling point in roughly ten seconds while still
  needing the caption/paper for technical detail.
- Before real results exist, show a clearly conceptual no-number illustration.
  Never depict a predicted success as an observed output.

## Pipeline and overview grammar

An overview is a scientific visual argument, not a software diagram. Domain evidence
must dominate: pose sequences, trajectories, temporal spans, masks, observations,
geometric overlays, contact schedules, token streams, feature maps, or other objects
that are native to the paper's problem. Use at least three such visual primitives.
Ordinary labeled boxes, cards, badges, and connector-only regions may occupy at most
35% of the canvas. If the method can be redrawn with different labels and still look
unchanged, reject it as a generic flowchart.

- Establish one dominant left-to-right or top-to-bottom spine. Auxiliary,
  gradient, control, and repair paths must use distinct line styles and remain
  subordinate.
- Group modules by semantic phase, not merely by implementation file. Repeated
  elements align to a visible grid.
- Reserve the largest or highest-contrast region for the novel mechanism.
  Standard components may collapse into a single neutral block.
- Prefer one macro-to-micro inset at most. If two modules both need dense
  explanation, split them into separate figures rather than filling every corner.
- Route arrows around nodes. Reject crossings, shared ambiguous paths, detached
  arrowheads, unnecessary outer loops, and feedback edges that dominate the
  forward path.
- Keep a compact rectangular silhouette. Protruding badges, legends, or loop
  labels that create dead corners are blocking defects.
- Use shape and line semantics consistently: data/process/state should not change
  visual language arbitrarily, and one color must not mean both failure and a
  method module.

## Candidate and refinement loop

For teasers and overviews, a single generation is never production-ready.

1. Hold the claim, labels, evidence status, and color semantics fixed. Create six
   genuinely different composition directions through separate imagegen calls.
   Cover at least three archetypes: domain-evidence/storyboard, continuous mechanism
   canvas, problem-versus-method narrative, macro-to-micro inset, spatial/topological
   map, or another role-appropriate grammar. Vary layout grammar and metaphor, not
   only palette, panel rhythm, or box placement.
2. Inspect every candidate at its intended physical paper width. Select using the
   rubric below; do not choose from full-screen appearance alone.
3. Apply at least three single-change imagegen edits to the selected direction.
   Typical edits repair hierarchy, arrow routing, label burden, empty corners, or
   final-size legibility.
4. Record counts in the selected prompt as `Candidate directions evaluated:` and
   `Targeted refinements completed:`. Counts below six and three respectively are
   blocking.

Do not retroactively expand an exact prompt after an imagegen call. For a narrow
single-change edit, say what changes and that all other content/composition must
be preserved. The edit may inherit the reference, composition, candidate-count,
and critic evidence from its direct parent only through a prompt/output
hash-bound provenance chain. Any broken lineage or broader redesign starts a new
full-contract prompt and critic pass.

## Independent critic rubric

Record every line below as `pass` or `fail` in the selected QA note:

- `Faithfulness`: no invented module/connection, logical reversal, scope drift,
  fake notation, or altered qualitative evidence.
- `Conciseness`: high visual signal-to-noise; no paragraph boxes, Method pasted
  into cards, or equation dump.
- `Readability`: obvious reading order, legible final-size labels, unambiguous
  arrows, adequate contrast, and no overlap.
- `Aesthetics`: consistent typography/geometry, restrained palette, deliberate
  spacing, and no generic presentation-template or clip-art look.
- `Domain evidence`: at least three problem-native visual primitives carry the
  scientific story; labels and containers do not do all explanatory work.
- `Non-generic composition`: ordinary module boxes occupy no more than 35% and the
  figure would not remain semantically unchanged after arbitrary relabeling.
- `Three-glance hierarchy`: the first glance conveys the claim, the second reveals
  mechanism/evidence, and the third rewards close inspection without microtext.
- `Novelty salience`: the visual hierarchy matches the paper's actual novelty.
- `Rectangular efficiency`: balanced bounding box without protrusions, dead
  corners, or a large unused row/column.
- `Final-size inspection`: the raster has been inspected inside the compiled PDF
  at the actual column/page width.

Hard vetoes include black backgrounds, neon grouping fills, figure title or full
caption baked into pixels, watermarks, illegible or inconsistent font sizes,
spaghetti arrows, malformed text, decorative 3D without semantic purpose,
corporate-blog card grids, and a diagram in which all modules have equal weight.
Also veto a sparse icon row, a renamed SaaS architecture, or a pipeline whose visual
content is mostly rounded rectangles and arrows even when it is technically correct.
