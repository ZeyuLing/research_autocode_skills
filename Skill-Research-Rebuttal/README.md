# skill-rebuttal

[中文阅读](README_ZH.md)

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill that helps researchers organize peer review comments, generate visual mind maps, and write structured rebuttal responses for academic paper submissions.

## What It Does

When you receive reviewer comments for a conference/journal submission, this skill guides you through a three-phase workflow:

1. **Organize Reviews** — Parse raw reviewer comments, classify weaknesses into standard categories, and identify each reviewer's key concerns
2. **Generate Mind Map** — Create a draw.io diagram that visualizes all reviewer feedback in a structured tree layout
3. **Write Rebuttal** — Draft professional, per-reviewer responses following battle-tested rebuttal writing principles

You can start from any phase depending on what you need.

## Quick Start

### Install the Rebuttal Skill

Copy the skill directory to your Claude Code skills folder:

```bash
# Global installation (available in all projects)
cp -r skills/rebuttal ~/.claude/skills/rebuttal

# Or project-level installation
mkdir -p .claude/skills
cp -r skills/rebuttal .claude/skills/rebuttal
```

Restart your Claude Code session. The skill will be available automatically.

### Install the draw.io Skill (Optional but Recommended)

The rebuttal skill generates `.drawio` files. For better diagram quality, install the [draw-io skill](https://github.com/softaworks/agent-toolkit/tree/main/skills/draw-io) as well:

```bash
git clone --depth 1 https://github.com/softaworks/agent-toolkit.git /tmp/agent-toolkit
cp -r /tmp/agent-toolkit/skills/draw-io ~/.claude/skills/draw-io
rm -rf /tmp/agent-toolkit
```

### View draw.io Files in Your IDE

You can view and edit the generated `.drawio` files directly in VS Code or Cursor by installing the **Draw.io Integration** extension:

1. Open VS Code / Cursor
2. Go to Extensions (`Ctrl+Shift+X` / `Cmd+Shift+X`)
3. Search for **"Draw.io Integration"** (by Henning Dieterichs)
4. Click Install

After installation, simply open any `.drawio` file and it will render as an interactive diagram in your editor.

### Usage

Just paste your reviewer comments into Claude Code and describe what you need:

```
# Full workflow
I submitted to CVPR and got 3 reviews, help me with the rebuttal.
[paste reviewer comments here]

# Organize reviews only
Help me organize these reviews
[paste reviewer comments]

# Generate mind map only
Generate a drawio diagram from these reviews

# Write rebuttal only
I've already organized the reviews, help me write a rebuttal
```

## Example

Here's a concrete example of the full workflow. Given these reviewer comments:

**Input:**

```
Reviewer 1 (Score: 5, Confidence: 4):
Weaknesses: The method is a straightforward combination of NeRF and diffusion model.
The novelty is limited as similar integration has been explored. Experiments are only
conducted on synthetic datasets, which limits the practical value of this work.

Reviewer 2 (Score: 6, Confidence: 3):
Weaknesses: The writing is generally clear, but the paper lacks comparison with the
recent Method-X (CVPR 2025). The ablation study is insufficient — only one component
is ablated while the method has three major modules.

Reviewer 3 (Score: 4, Confidence: 5):
Weaknesses: The assumption that scenes are static is unrealistic for most real-world
applications. The improvement over the baseline is only 0.5dB PSNR, which is marginal.
```

**Phase 1 Output — Review Summary:**

```markdown
## Review Summary

### Reviewer 1 (Score: 5; Confidence: 4)
| Category | Specific Issue | Priority |
|----------|---------------|----------|
| Insufficient Contribution | Straightforward combination of NeRF + diffusion, novelty limited | **Key** |
| Insufficient Evaluation | Only synthetic datasets, no real-world experiments | Normal |

### Reviewer 2 (Score: 6; Confidence: 3)
| Category | Specific Issue | Priority |
|----------|---------------|----------|
| Insufficient Evaluation | Missing comparison with Method-X; ablation only covers 1 of 3 modules | **Key** |

### Reviewer 3 (Score: 4; Confidence: 5)
| Category | Specific Issue | Priority |
|----------|---------------|----------|
| Method Design Flaws | Static scene assumption is unrealistic | **Key** |
| Weak Experimental Results | Only 0.5dB PSNR improvement over baseline | Normal |
```

**Phase 2 Output — draw.io mind map** (`.drawio` file with tree structure, key concerns in red)

**Phase 3 Output — Rebuttal Draft:**

```markdown
## Response to Reviewer 1

We thank Reviewer 1 for the constructive feedback.

### [R1-W1] Novelty of NeRF + Diffusion Integration

Our method differs from naive combinations in three key aspects.
First, we introduce [specific technique] that enables [specific capability],
which prior NeRF-diffusion works cannot achieve (see ablation in Table 3).
Second, ...

### [R1-W2] Evaluation on Real-World Data

We have conducted additional experiments on [real-world dataset].
Results show our method achieves [X] PSNR / [Y] SSIM, outperforming
the baseline by [Z]dB. We will include these results in the revision.
```

## Weakness Categories

The skill classifies reviewer concerns into six standard categories:

| Category | Description |
|----------|-------------|
| **Insufficient Contribution** | Insufficient novelty — techniques well-explored, improvements predictable, approach straightforward |
| **Unclear Writing** | Unclear writing — missing technical details, not reproducible, lacking motivation |
| **Weak Experimental Results** | Insufficient results — marginal improvements, results not convincing enough |
| **Method Design Flaws** | Method design flaws — unrealistic settings, technical defects, poor robustness |
| **Insufficient Evaluation** | Insufficient evaluation — missing ablations, baselines, metrics, or datasets |
| **Justification Breakdown** | Decomposition of the reviewer's scoring rationale |

## Rebuttal Writing Principles

The skill follows these core principles, distilled from experienced researchers:

1. **Give them what they ask for** — If they want ablations, provide ablations. Don't argue about whether the request is reasonable.
2. **Don't introduce new problems** — Every new claim is a potential attack surface. Stay focused.
3. **Answer directly** — Start each response by addressing the reviewer's point head-on.
4. **Make it skimmable** — Reviewers won't re-read their own reviews. Each response should be self-contained.
5. **Focus on key concerns** — Each reviewer has 1-2 core concerns that determine their score. Nail those.

## Project Structure

```
skill-rebuttal/
├── README.md                              # This file
├── README_ZH.md                           # 中文文档
├── LICENSE                                # MIT License
├── skills/
│   └── rebuttal/
│       ├── SKILL.md                       # Main skill instructions
│       ├── references/
│       │   ├── drawio-template.md         # draw.io XML template spec
│       │   └── rebuttal-guide.md          # Rebuttal writing strategies
│       └── assets/
│           └── rebuttal-template.drawio    # Original draw.io template
└── docs/
    └── rebuttal-methodology.md            # Source methodology document
```

## Disclaimer

This project is intended solely as an **assistive tool** for drafting rebuttal responses. The generated content should be used as a starting point and reference only. Please do **not** submit the output directly as a formal rebuttal — always review, revise, and verify all content with your co-authors before submission.

## Credits

- Rebuttal methodology based on [pengsida/learning_research](https://github.com/pengsida/learning_research)
- Writing strategies adapted from [Devi Parikh's rebuttal guide](https://deviparikh.medium.com/how-we-write-rebuttals-dc84742fece1) and [SIGGRAPH rebuttal guide](https://research.siggraph.org/blog/guides/writing-a-rebuttal-for-siggraph/)

## License

[MIT](LICENSE)
