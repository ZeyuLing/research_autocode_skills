# Research AutoCode Skills

A curated collection of Claude Code / Codex / Cursor skills for AI-assisted research workflows — from paper writing and figure generation to automated debugging and GPU cluster management.

## Skills Overview

| Skill | Description | Platforms |
|-------|-------------|-----------|
| [autodebug](#autodebug) | Hypothesis-driven iterative auto-debugging | Claude Code |
| [pua](#pua) | High-agency enforcement — forces the AI to exhaust all options before giving up | Claude Code, Codex, Cursor, Kiro, and more |
| [idea2paper](#idea2paper) | End-to-end idea-to-experiment-ready LaTeX paper workflow | Codex |
| [nature-paper-card](#nature-paper-card) | Source-grounded, module-by-module deep reading of AI and scientific papers | Claude Code, Codex, Cursor |
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

## idea2paper

**Turn a research idea into a complete, experiment-ready LaTeX paper sketch.**

- Selects the nearest suitable conference with an open abstract deadline from the strict default pool (ECCV, ICCV, CVPR, NeurIPS/NIPS, ICML, ICLR, AAAI, IJCAI, ACM MM/ACMMM, ACL, EMNLP), verifies official rules and templates, and tracks a previous-cycle template when the current one is unavailable
- Invokes `ai-literature-survey` for source-audited prior-art discovery, including publication, paper-access, code, data, and model-weight status; a full sketch now requires at least 30 included local papers, 20 distinct corpus citations in Related Work, five coverage families, eight recent works, eight accepted/published works, three novelty-risk records, and a complete core-paper reading matrix
- Runs independent novelty and feasibility reviews followed by Professor adjudication before freezing claims and contributions
- Designs the Method, benchmark tables, baselines, metrics, ablations, qualitative results, and linked predicted-result TODOs
- Generates diverse paper-title candidates, checks prior-title collisions, runs independent positioning and faithfulness reviews, and freezes a title bound to the final claims and Method
- Drafts Related Work, Introduction, Abstract, Conclusion, appendix material, and all content except measured experimental data
- Uses the system `imagegen` skill exclusively for every paper figure, including overviews, modules, teasers, charts, qualitative layouts, and placeholders; every qualitative TODO must be bound inside the same float as an audited ImageGen raster, result ID, prompt, provenance, QA record, and the exact `CONCEPTUAL PLACEHOLDER - REPLACE WITH RAW OUTPUTS` disclosure until raw outputs replace it; teaser/overview generation is reference-driven and claim-first, with six directions across at least three composition archetypes, domain-native visual evidence, a 35% cap on generic module boxes, three targeted refinements, independent visual critics, and final-size PDF inspection
- Enforces the rendered front-matter order `Title -> Authors -> Teaser -> Abstract` by placing one non-floating teaser immediately after `\maketitle`, leaving the official venue style file unchanged and avoiding brittle template-internal patches
- Enforces one artifact per LaTeX source file: every figure, table, teaser, and source-anchored `\captionof` unit lives in its own `paper/figures/*.tex` or `paper/tables/*.tex`, while section and appendix files preserve placement with one `\input` per artifact
- Uses `paperjury:paperjury` for at least two isolated, adversarial review rounds with three reviewer lenses, schema-v2 structured major findings with frozen-snapshot-resolved file-line/label evidence and fix provenance, exact-hash-only legacy migration, an adjudicated issue ledger, and a final review bound to the manuscript hash
- Validates claim-method-experiment coverage, terminology, citations, page budget, snapshot-portable tracked TODO paths/lines/messages, state invalidation, LaTeX readiness, canonical section boundaries with optional Limitations before a truly final Conclusion, body/appendix floating and source-anchored `\captionof` artifact labeling, fresh compiler-log/AUX binding, independently recomputed column/artifact/whitespace/reading-continuity gates, TeX clipping/overfull boxes, unsuppressed diagnostics, PDF media-box overflow, word- or sentence-interrupting top artifacts, single-column leading/internal/trailing blank regions, sparse terminal artifact pages, per-page overload, appendix-tail clustering, manual pagination/forced `[H]` placement, and post-Conclusion spill
- Includes offline regression tests; requires Python 3.10+ plus `pdfplumber` from `idea2paper/requirements.txt` for rendered page-geometry auditing (use a real runtime, not the Windows Store alias)
- Requires `ai-literature-survey`, `paperjury:paperjury`, and the system `imagegen` skill; `idea2paper` stops instead of silently substituting another literature, review, or figure workflow when a dependency is unavailable

**Trigger**: `idea2paper`, "turn this idea into a paper", "paper sketch", "from idea to paper", "从 idea 写论文", "一键写论文"

---

## research-paper-writing

**Section-by-section academic writing guidance for ML/CV/NLP papers.**

- Section-specific rules for Introduction, Abstract, Related Work, Method, Experiments, Conclusion
- Global principles: one message per paragraph, explicit topic sentences, sentence-level flow
- Paragraph clarity check via reverse outlining
- 5-dimension pre-submission self-review: contribution, writing clarity, experimental strength, evaluation completeness, method design
- Claim-evidence alignment checking

---

## nature-paper-card

**Evidence-grounded deep reading for a single AI or scientific paper.**

- Reconstructs the scientific problem and why existing approaches are insufficient
- Maps every central module or strategy to its function, necessity, inputs/outputs, assumptions, and ablation evidence
- Traces the causal chain from prior-work limitations through the paper's design choices to the conclusions actually supported
- Separates paper claims, external facts, analysis, and hypotheses with stable source pointers
- Includes local PDF/source-map preparation, a fixed 16-section Paper Card schema, and a groundedness auditor

**Trigger**: "deep-read this paper", "analyze every module", "generate a Paper Card", "精读这篇论文"

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

**Routing note**: inside an `idea2paper` workflow, the imagegen-only contract takes precedence; this skill must not be used for paper figures.

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

Standalone skills can be installed by copying their directory into the agent's skill directory. Orchestrator skills may declare hard dependencies: `idea2paper` additionally requires `ai-literature-survey`, `paperjury:paperjury`, and Codex's system `imagegen` skill. For Codex, use `$CODEX_HOME/skills`; for Claude Code, use `.claude/skills`. Standalone wrapper repositories may include additional platform-specific instructions.
