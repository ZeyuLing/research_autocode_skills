# Upstream research and provenance

This skill is an original implementation informed by a GitHub survey. No upstream source file is vendored.

## Sources studied

1. [OvOhao/auto-paper-collecter](https://github.com/OvOhao/auto-paper-collecter) (MIT): a Codex-compatible skill with multi-source discovery, deduplication, Markdown/HTML rendering, and several notification channels. This skill adopts the general idea of source normalization plus channel-independent artifacts.
2. [ramazan793/research-radar](https://github.com/ramazan793/research-radar) (MIT): a two-pass workflow that first scores abstracts and then reads PDFs for top candidates. This skill adopts the abstract-triage/full-text-review separation.
3. [lyndonkl/claude paper-relevance-filter](https://github.com/lyndonkl/claude/tree/main/skills/paper-relevance-filter): emphasizes that relevance is not scientific quality. This skill makes that separation explicit in its gates and score report.

## Material differences

- domain-specific hard gates and collision terms
- independent relevance, intrinsic-quality, and external-signal scores
- full-text evidence requirement for highlights
- explicit scientific-problem, prior-work-gap, and module-to-problem fields
- per-topic diversity caps
- explicit source-failure and query-cap coverage accounting
- seen-state mutation only after an acknowledged local delivery or successful delivery to every requested external channel
- structured source, selection, and delivery reports
- v2 artifact lanes for recent papers, curated foundational classics, and verified Hugging Face open-model releases
- high-precision audiovisual relationship matching plus artifact-, lane-, and primary-topic-scoped post-quality quotas that never lower evidence gates or override hard caps

Check upstream licenses and behavior again before copying code or adding new vendored components. Links and license observations were verified during initial development in August 2026.
