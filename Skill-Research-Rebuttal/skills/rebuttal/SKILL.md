---
name: rebuttal
description: Academic paper rebuttal assistant. Helps researchers organize reviewer comments, generate draw.io mind maps for visual overview, and write structured rebuttal responses. Use this skill whenever users mention rebuttal, reviewer comments, paper reviews, peer review responses, author response, addressing reviewer concerns, or need to organize/respond to academic review feedback — even if they just paste review text without explicitly saying "rebuttal".
---

# Academic Rebuttal Assistant

Help researchers go from raw reviewer comments to a polished rebuttal, with visual organization along the way.

## Workflow Overview

The rebuttal process has three phases. Determine which phase the user is in based on what they provide, and pick up from there.

### Phase 1: Organize Reviews

**When**: User provides raw reviewer comments (pasted text, PDF, or file).

**Goal**: Understand *why* each reviewer gave their score. Reviewers typically have 1-2 core concerns they care most about — everything else is secondary. Identifying these core concerns early is critical because they determine whether the reviewer will change their score.

**Steps**:

1. Parse each reviewer's comments and extract:
   - Score and confidence level
   - Justification (the reasoning behind their score — this reveals their core concerns)
   - Individual weakness points

2. Classify each weakness into one of these categories:
   - **Insufficient Contribution** — Paper doesn't bring enough new knowledge (failure cases are common, techniques are well-explored, improvements are predictable, approach is straightforward)
   - **Unclear Writing** — Writing lacks clarity (missing technical details, not reproducible, modules lack motivation)
   - **Weak Experimental Results** — Experimental results insufficient (marginal improvements over baselines, results still not good enough overall)
   - **Method Design Flaws** — Method design flaws (unrealistic settings, technical defects, not robust, new limitations outweigh benefits)
   - **Insufficient Evaluation** — Insufficient evaluation (missing ablations, important baselines, key metrics, data too simple)
   - **Justification Breakdown** — Decomposition of the reviewer's scoring rationale

3. Identify and mark the **key concerns** for each reviewer — usually 1-2 points that are most prominent in their justification. These are the points the reviewer will remember and care about most during the discussion phase.

4. Output a structured Markdown summary:

```markdown
## Review Summary

### Reviewer 1 (Score: 5; Confidence: 4)

**Justification Key Points**:
- The method is a straightforward combination of NeRF and diffusion model
- **Insufficient novelty — Key Concern**

**Weakness Classification**:

| Category | Specific Issue | Priority |
|----------|---------------|----------|
| Insufficient Contribution | The proposed technique has been well-explored, the improvement is predictable | Key |
| Insufficient Evaluation | Only evaluated on synthetic datasets, missing real-world experiments | Normal |
| ... | ... | ... |
```

Save the review summary as a `.md` file (e.g., `review-summary.md` or a user-specified filename).

### Phase 2: Generate draw.io Mind Map

**When**: User asks for a visual overview, or after Phase 1 is complete.

**Goal**: Create a draw.io diagram following the Rebuttal template structure — a tree map with the root being "Reviewer Weaknesses", branching to each reviewer, then to weakness categories, then to specific review points.

Read the template reference file for the exact XML structure:
→ **Read `references/drawio-template.md`** before generating any drawio file.

Key rules for the diagram:
- Root node "Reviewer Weaknesses" on the left
- Each reviewer (R1, R2, R3...) as second-level nodes showing score and confidence
- Six category nodes per reviewer (Justification Breakdown, Insufficient Contribution, Unclear Writing, Weak Experimental Results, Method Design Flaws, Insufficient Evaluation)
- Specific review points as leaf nodes on the right
- **Mark key concerns in red** (`fillColor=#f8cecc;strokeColor=#b85450`)
- After each leaf node, append the **original review text** as a quote block or a separate text node so the reviewer's exact wording is preserved alongside the categorized summary
- Use `fontFamily=Helvetica` on all text elements
- Edges use `edgeStyle=orthogonalEdgeStyle;curved=1`
- Set `page="0"` for transparent background

Save the output as `rebuttal-review-map.drawio` (or a user-specified filename).

### Phase 3: Write Rebuttal Responses

**When**: User has organized reviews (from Phase 1 or their own) and wants to draft responses.

**Goal**: Write clear, direct rebuttal responses that address each reviewer's concerns.

**Core principles** — these come from experienced researchers and are battle-tested:

1. **Give them what they ask for.** If they want ablations, provide ablations. If they want comparisons, provide comparisons. Don't argue about whether the request is reasonable — just answer it.

2. **Don't introduce new problems.** Every claim in the rebuttal is a surface for new attacks. Keep responses focused and self-contained. Don't volunteer information that wasn't asked for.

3. **Answer directly.** Start each response by directly addressing the reviewer's point. The reviewer should immediately see that you're answering *their* specific question, not dancing around it.

4. **Skimmable and self-contained.** Reviewers won't re-read their own reviews when reading your rebuttal. Each response should make sense on its own without requiring the reader to look up the original comment.

5. **Focus effort on key concerns.** After drafting all responses, double-check that the 1-2 key concerns per reviewer are answered convincingly. These determine whether the reviewer changes their score.

**Response format for each reviewer**:

```markdown
## Response to Reviewer [N]

We thank Reviewer [N] for the constructive feedback.

### [R{N}-W1] [Brief description of the concern]

[Direct response addressing the concern]

### [R{N}-W2] [Brief description]

[Response]

...
```

**Tone guidelines**:
- Professional and respectful, like a Q&A discussion
- Never condescending or confrontational, even if the reviewer misunderstood something
- When the reviewer is wrong, gently redirect: "We appreciate this question. To clarify, [correct information]..."
- When making commitments for the camera-ready version, only promise what you can actually deliver

**Output**: Save the rebuttal draft as a `.md` file (e.g., `rebuttal-draft.md` or a user-specified filename). This makes it easy to further edit, share, and convert to other formats.

## Language Handling

Detect the language of the user's input and respond in the same language throughout the entire workflow.

- If the user writes in **Chinese** (e.g., "帮我做rebuttal", "整理这些review"), all output — review summaries, analysis, commentary, and rebuttal strategy notes — should be in Chinese. The rebuttal response text itself should still be in English (since rebuttals are submitted in English to conferences), but all surrounding explanation and structural labels use Chinese. The draw.io diagram should use **Chinese labels** for category nodes (贡献不足, 写作不清楚, 实验效果不够好, 方法设计有问题, 评测不充分, Justification拆解).
- If the user writes in **English** (e.g., "help me write a rebuttal", "organize these reviews"), all output — summaries, analysis, labels, and rebuttal text — should be in English. The draw.io diagram should use **English labels** for category nodes (Insufficient Contribution, Unclear Writing, Weak Experimental Results, Method Design Flaws, Insufficient Evaluation, Justification Breakdown).

**Chinese output example**:
```markdown
## Review 整理

### 审稿人 1 (分数: 5; Confidence: 4)

**Justification核心观点**:
- The method is a straightforward combination of existing techniques
- **Novelty不足 — 重点问题**

**Weaknesses分类**:

| 类别 | 具体问题 | 重要程度 |
|------|---------|---------|
| 贡献不足 | The proposed technique has been well-explored | 重点 |
| 评测不充分 | Missing evaluation on real-world datasets | 普通 |
```

**English output example**:
```markdown
## Review Summary

### Reviewer 1 (Score: 5; Confidence: 4)

**Key Justification Points**:
- The method is a straightforward combination of existing techniques
- **Insufficient novelty — Key Concern**

**Weakness Classification**:

| Category | Specific Issue | Priority |
|----------|---------------|----------|
| Insufficient Contribution | The proposed technique has been well-explored | Key |
| Insufficient Evaluation | Missing evaluation on real-world datasets | Normal |
```

## Handling Partial Inputs

Users may enter at any phase:
- **Just pasted review text** → Start from Phase 1
- **"帮我整理这些review"** / **"organize these reviews"** → Phase 1
- **"帮我画个drawio图"** / **"generate a drawio diagram"** → Phase 2 (ask for review content if not provided)
- **"帮我写rebuttal"** / **"help me write a rebuttal"** → Phase 3 (ask for organized reviews if not available)
- **"帮我做rebuttal"** / **"help me with my rebuttal"** → Full workflow from Phase 1

## Reference Files

- `references/drawio-template.md` — draw.io XML template structure and node layout specs. Read this before generating any drawio file.
- `references/rebuttal-guide.md` — Detailed rebuttal writing strategies from Devi Parikh and SIGGRAPH guides. Read this when drafting rebuttal responses for additional tactical advice.
