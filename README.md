# Research AutoCode Skills

A curated collection of Claude Code / Codex / Cursor skills for AI-assisted research workflows — from paper writing and figure generation to automated debugging and GPU cluster management.

## Skills Overview

| Skill | Description | Platforms |
|-------|-------------|-----------|
| [autodebug](#autodebug) | Hypothesis-driven iterative auto-debugging | Claude Code |
| [pua](#pua) | High-agency enforcement — forces the AI to exhaust all options before giving up | Claude Code, Codex, Cursor, Kiro, and more |
| [remote-exec](#remote-exec) | GPU server management & distributed task execution | Claude Code |
| [research-paper-writing](#research-paper-writing) | Academic paper writing & self-review guidance | Claude Code, Codex, Cursor, OpenCode |
| [Research-Paper-Writing-Skills](#research-paper-writing-skills) | Standalone repo wrapper for `research-paper-writing` | Claude Code, Codex, Gemini |
| [Skill-Research-Figure](#skill-research-figure) | Publication-quality TikZ diagrams & Blender 3D renders | Claude Code |
| [Skill-Research-Rebuttal](#skill-research-rebuttal) | Peer review organization, mind maps & rebuttal drafting | Claude Code |

---

## autodebug

**Iterative automated debugging with ReAct decision cycles.**

- Three-file memory system: `brief.md` (context), `history.md` (iteration log), `insights.md` (active hypotheses)
- Priority-based action selection: P1 crash fix → P2 infrastructure → P3 hypothesis-driven → P4 exploratory
- Automatic code backup per iteration (`backups/iter_N/`)
- Built-in anti-loop mechanism to avoid repeating failed approaches
- External loop runners for non-interactive (`run_loop.py`) and interactive (`run_loop_interactive.py`) usage

**Trigger**: `/autodebug`, `自动调试`, `debug loop`, `迭代调试`

---

## pua

**High-agency AI enforcement using corporate PUA / PIP rhetoric.**

Pushes the AI coding agent to exhaust every possible solution before admitting defeat. Three iron rules: (1) exhaust all options, (2) act before asking, (3) take initiative.

- 4-level pressure escalation: mild disappointment → soul interrogation → 361 review → graduation warning
- 5-step debugging methodology: Smell → Elevate → Mirror Check → Execute → Retrospective
- Corporate PUA expansion pack: Alibaba, ByteDance, Huawei, Tencent, Meituan, Netflix, Musk, Jobs flavors
- High-Agency v2: internal drive + external pressure with recovery protocols & cross-session learning
- Multi-language support: Chinese (default), English (PIP Edition), Japanese

**Platforms**: Claude Code, Codex CLI, Cursor, Kiro, OpenClaw, Google Antigravity, OpenCode

---

## remote-exec

**GPU server management & task tracking for shared-storage clusters.**

- 8 pre-configured GPU servers (A100, V100, A800 variants) with apdcephfs shared storage
- Live GPU status, occupancy & process classification (TRAINING / other / idle)
- Smart command routing: debug → local, large-scale → remote
- Task registration & lifecycle tracking
- Predefined shortcuts: `debug10`, `debug100`, `nvidia_smi`, `gpu_stat`, `kill_python`, etc.

**Commands**: `status [target]`, `run [@target] <cmd>`, `kill [@target|all]`, `refresh`

---

## research-paper-writing

**Section-by-section academic writing guidance for ML/CV/NLP papers.**

- Section-specific rules for Introduction, Abstract, Related Work, Method, Experiments, Conclusion
- Global principles: one message per paragraph, explicit topic sentences, sentence-level flow
- Paragraph clarity check via reverse outlining
- 5-dimension pre-submission self-review: contribution, writing clarity, experimental strength, evaluation completeness, method design
- Claim-evidence alignment checking

---

## Research-Paper-Writing-Skills

Standalone repository wrapper that packages the `research-paper-writing` skill with cross-platform installation instructions (Claude Code, Codex, Gemini).

---

## Skill-Research-Figure

**Publication-quality research figures through TikZ and Blender.**

- **TikZ pipeline figures**: method overview, flowcharts, architecture diagrams with auto-compile & self-check
- **Blender 3D renders**: SMPL/FBX mesh rendering, skeleton visualization, teaser figures, 3D comparisons
- 5 color schemes (Blue-Gray, Warm Tones, Green-Cyan, Purple-Blue, Monochrome)
- 5 layout templates (linear H/V, loop/U-shape, two-stage, multi-branch)
- Card-based design with low-saturation colors, highlight of novel contributions

**Trigger**: "method figure", "pipeline figure", "architecture diagram", "teaser", "3D render", "SMPL", "Blender", "画图", etc.

---

## Skill-Research-Rebuttal

**Peer review organization, mind map generation & structured rebuttal writing.**

Three-phase workflow:
1. **Organize** — classify reviewer weaknesses into 6 standard categories (insufficient contribution, unclear writing, weak experiments, method design flaws, insufficient evaluation, justification breakdown)
2. **Mind Map** — generate a draw.io diagram visualizing all feedback at a glance
3. **Rebuttal** — draft professional, per-reviewer responses following rebuttal best practices (answer directly, make it skimmable, focus on key concerns)

**Trigger**: paste reviewer comments, then ask to "organize reviews", "generate mind map", or "write rebuttal"

---

## Installation

Each skill can be installed independently. Most skills for Claude Code are installed by adding the skill directory to your project's `.claude/skills/` or via the slash command configuration. See each skill's own README for platform-specific instructions.
