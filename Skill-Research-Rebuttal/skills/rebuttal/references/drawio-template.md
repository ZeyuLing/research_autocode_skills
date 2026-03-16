# draw.io Rebuttal Template Reference

This file defines the exact XML structure for generating rebuttal review mind maps. The diagram is a left-to-right tree with four levels.

## Layout Structure

```
Level 0 (x=-546)     Level 1 (x=-194)     Level 2 (x=72)              Level 3 (x=601)
┌──────────────┐     ┌──────────┐         ┌────────────────────┐      ┌─────────────────┐
│   Reviewer    │────▶│ R1       │────────▶│ Justification       │─────▶│ Point 1          │
│  Weaknesses  │     │(Score;Cf)│         │ Breakdown           │      ├─────────────────┤
└──────────────┘     └──────────┘         ├────────────────────┤      │ Point 2          │
                     ┌──────────┐         │ Insufficient        │      ├─────────────────┤
                ────▶│ R2       │         │ Contribution        │─────▶│ ...              │
                     │(Score;Cf)│         ├────────────────────┤      └─────────────────┘
                     └──────────┘         │ Unclear Writing     │
                     ┌──────────┐         ├────────────────────┤
                ────▶│ R3       │         │ Weak Experimental   │
                     │(Score;Cf)│         │ Results             │
                     └──────────┘         ├────────────────────┤
                                          │ Method Design Flaws │
                                          ├────────────────────┤
                                          │ Insufficient        │
                                          │ Evaluation          │
                                          └────────────────────┘
```

## Vertical Spacing

Each reviewer section is approximately 650-850px tall. Reviewers are stacked vertically:
- R1: y starts around -319 (top of Justification) to ~600 (bottom of Insufficient Evaluation)
- R2: y starts around 628 to ~1340
- R3: y starts around 1478 to ~2156

Within each reviewer, categories are spaced ~120-160px apart vertically. Leaf nodes within a category are spaced ~80px apart.

## Node Dimensions

| Node Type | Width | Height |
|-----------|-------|--------|
| Root (Weaknesses) | 120 | 60 |
| Reviewer (R1/R2/R3) | 120 | 60 |
| Category | 421 | 80 |
| Leaf (specific review) | 205 | 60 |
| Original review text | 250 | 60 |

## XML Template

```xml
<mxfile host="Electron" agent="draw.io" version="28.2.7">
  <diagram name="Review整理" id="rebuttal-map">
    <mxGraphModel dx="2954" dy="1762" grid="0" gridSize="10" guides="1"
      tooltips="1" connect="1" arrows="1" fold="1" page="0"
      pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />

        <!-- === EDGES FIRST (render behind boxes) === -->

        <!-- Root → Reviewer edges -->
        <mxCell id="edge-root-r1" style="edgeStyle=orthogonalEdgeStyle;curved=1;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" edge="1" parent="1" source="root" target="r1">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Reviewer → Category edges (repeat for each category per reviewer) -->
        <mxCell id="edge-r1-cat1" style="edgeStyle=orthogonalEdgeStyle;shape=connector;curved=1;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;entryX=0;entryY=0.5;entryDx=0;entryDy=0;strokeColor=default;align=center;verticalAlign=middle;fontFamily=Helvetica;fontSize=11;fontColor=default;labelBackgroundColor=default;endArrow=classic;" edge="1" parent="1" source="r1" target="r1-justification">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- Category → Leaf edges (repeat for each leaf) -->
        <mxCell id="edge-r1-cat1-leaf1" style="edgeStyle=orthogonalEdgeStyle;shape=connector;curved=1;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;entryX=0;entryY=0.5;entryDx=0;entryDy=0;strokeColor=default;align=center;verticalAlign=middle;fontFamily=Helvetica;fontSize=11;fontColor=default;labelBackgroundColor=default;endArrow=classic;" edge="1" parent="1" source="r1-justification" target="r1-just-point1">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

        <!-- === VERTICES (render in front) === -->

        <!-- Root node -->
        <mxCell id="root" value="Reviewer&lt;div&gt;Weaknesses&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="-546" y="832" width="120" height="60" as="geometry" />
        </mxCell>

        <!-- Reviewer nodes -->
        <mxCell id="r1" value="R1&lt;div&gt;(Score; Confidence)&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="-194" y="174" width="120" height="60" as="geometry" />
        </mxCell>

        <!-- Category nodes (per reviewer) -->
        <mxCell id="r1-justification" value="Justification Breakdown" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="72" y="-319" width="421" height="80" as="geometry" />
        </mxCell>

        <mxCell id="r1-contribution" value="Insufficient Contribution&lt;div&gt;(Paper doesn't bring enough new knowledge: failure cases are common, techniques well-explored, improvements predictable, approach straightforward)&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="72" y="-160" width="421" height="80" as="geometry" />
        </mxCell>

        <mxCell id="r1-writing" value="Unclear Writing (missing technical details, not reproducible, modules lack motivation)" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="72" y="-1" width="421" height="80" as="geometry" />
        </mxCell>

        <mxCell id="r1-results" value="Weak Experimental Results (marginal improvements over baselines, results still not good enough overall)" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="72" y="158" width="421" height="80" as="geometry" />
        </mxCell>

        <mxCell id="r1-method" value="Method Design Flaws (unrealistic settings, technical defects, not robust, new limitations outweigh benefits)" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="72" y="317" width="421" height="80" as="geometry" />
        </mxCell>

        <mxCell id="r1-eval" value="Insufficient Evaluation (missing ablation studies, important baselines, key metrics, data too simple)" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="72" y="476" width="421" height="80" as="geometry" />
        </mxCell>

        <!-- Leaf nodes (specific review points) -->
        <!-- Normal leaf -->
        <mxCell id="r1-just-point1" value="R1&lt;div&gt;Justification Point 1&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fontFamily=Helvetica;fontSize=11;fontColor=default;labelBackgroundColor=default;" vertex="1" parent="1">
          <mxGeometry x="601" y="-372" width="205" height="60" as="geometry" />
        </mxCell>

        <!-- Key concern leaf (RED background) -->
        <mxCell id="r1-just-point2-key" value="R1&lt;div&gt;Key Concern&lt;/div&gt;&lt;div&gt;(highlighted in red)&lt;/div&gt;" style="rounded=1;whiteSpace=wrap;html=1;fontFamily=Helvetica;fontSize=11;labelBackgroundColor=none;fillColor=#f8cecc;strokeColor=#b85450;" vertex="1" parent="1">
          <mxGeometry x="601" y="-290" width="205" height="60" as="geometry" />
        </mxCell>

        <!-- Original review text (placed next to leaf nodes to preserve reviewer's exact wording) -->
        <mxCell id="r1-just-original" value="[Paste original review text here]" style="text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;verticalAlign=top;rounded=0;fontFamily=Helvetica;fontSize=9;fontColor=#888888;labelBackgroundColor=default;" vertex="1" parent="1">
          <mxGeometry x="848" y="-316" width="250" height="60" as="geometry" />
        </mxCell>

      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

## Style Reference

### Edge style (all edges use the same style)
```
edgeStyle=orthogonalEdgeStyle;shape=connector;curved=1;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;entryX=0;entryY=0.5;entryDx=0;entryDy=0;strokeColor=default;align=center;verticalAlign=middle;fontFamily=Helvetica;fontSize=11;fontColor=default;labelBackgroundColor=default;endArrow=classic;
```

### Normal leaf node style
```
rounded=1;whiteSpace=wrap;html=1;fontFamily=Helvetica;fontSize=11;fontColor=default;labelBackgroundColor=default;
```

### Key concern (red) leaf node style
```
rounded=1;whiteSpace=wrap;html=1;fontFamily=Helvetica;fontSize=11;labelBackgroundColor=none;fillColor=#f8cecc;strokeColor=#b85450;
```

### Original review text style
```
text;html=1;whiteSpace=wrap;strokeColor=none;fillColor=none;align=left;verticalAlign=top;rounded=0;fontFamily=Helvetica;fontSize=9;fontColor=#888888;labelBackgroundColor=default;
```

## Generation Rules

1. **ID scheme**: Use descriptive IDs like `r1-contribution-leaf1`, `edge-r1-r1cat2`, etc.
2. **Edges before vertices**: All `<mxCell edge="1">` elements before any `<mxCell vertex="1">` elements.
3. **Dynamic reviewer count**: Generate as many reviewer sections as provided (not limited to 3).
4. **Dynamic leaf count**: Each category can have 0 or more leaf nodes based on actual review content. Skip categories with no matching weaknesses.
5. **Y-offset calculation**: For reviewer N (0-indexed), base Y = N * 850. Category offsets within reviewer are fixed relative to the base.
6. **Leaf Y-offset**: Within a category, leaf nodes are spaced 80px apart, starting at the same Y as the category node.
7. **Original review text**: Place the reviewer's original text (in gray, smaller font) next to each leaf node, positioned at x=848, width=250, y = leaf's y. This preserves the exact wording for reference.
