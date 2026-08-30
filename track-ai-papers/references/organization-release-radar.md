# Organization technical-release radar

Read this reference whenever the radar monitors releases from companies, research laboratories, frontier startups, open-source organizations, or developer platforms. This is a first-class discovery lane, not a fallback for a quiet arXiv day.

## Lane invariants

- Run `organization-release` alongside recent arXiv papers, verified conference publications, Hugging Face/open-model discovery, and foundational classics. No other lane can satisfy or replace its coverage obligation.
- A run with no eligible release is valid only after the organization lane was actually attempted and its coverage audit records `completed_no_eligible_release`.
- Keep organization and source coverage extensible. The seed matrix below bootstraps discovery; it is neither an allowlist nor an exhaustive market map.
- Deduplicate the artifact, not the evidence. A model found through an official announcement, official repository, and Hugging Face should be one candidate with three provenance records, not three releases.
- Reserve review capacity for high-signal organization releases, but never lower evidence, relevance, quality, openness, or safety gates to fill a quota.
- Do not force non-paper artifacts into paper terminology. A tool, SDK, API, standard, dataset, benchmark, research preview, or repository must be reviewed using its actual artifact type.

## Extensible coverage matrix

Start from every category relevant to the user. Expand the matrix during each run through official cross-links, newly observed first-party repositories, lab pages, and repeated high-signal releases. Preserve category membership as metadata because one organization can belong to more than one category.

| Category | Non-exhaustive seed organizations and programs | Typical signals |
|---|---|---|
| Global frontier labs and large platforms | OpenAI; Anthropic; Google DeepMind / Google Research; Meta AI; xAI; Microsoft Research / Azure AI; NVIDIA Research / Developer; Apple Machine Learning Research; Amazon Science / AWS AI; Mistral AI; Cohere; Hugging Face | model and API releases, research previews, system cards, SDKs, benchmarks, datasets, standards, major repositories |
| Chinese large platforms and frontier labs | Tencent / Hunyuan; ByteDance / Seed; Alibaba / Qwen / DAMO; Baidu / ERNIE / PaddlePaddle; Huawei / Noah's Ark / Pangu / Ascend; Moonshot AI / Kimi; MiniMax; Zhipu AI / GLM; DeepSeek; StepFun; Baichuan; 01.AI; Shanghai AI Laboratory / InternLM / OpenGVLab | foundation models, multimodal systems, agents, developer platforms, model weights, technical reports, benchmarks and datasets |
| Embodied AI, robotics and autonomous systems | Tesla AI; Physical Intelligence; Figure; 1X; Agility Robotics; Boston Dynamics; Skild AI; Covariant; Waabi | robot foundation models, VLA/policies, hardware-aware tools, simulation/data engines, autonomy stacks, evaluation suites and research demos with technical evidence |
| Generative media and world models | Runway; Luma AI; Pika; World Labs; Stability AI | image/video/audio generation, audiovisual systems, 3D/world models, editing tools, APIs, research previews, model releases and technical repositories |
| Developer tools and open platforms | Hugging Face and newly discovered first-party model/tool organizations; major compiler, inference, orchestration, evaluation and data-tool projects with verified maintainers | SDKs, inference engines, agent frameworks, evaluation harnesses, serving stacks, standards and important open-source repositories |

The names above are seeds. Do not conclude that the category is covered merely because every seed was checked. During discovery:

1. Follow first-party links to owned labs, product research pages, documentation changelogs, official repositories, model organizations, and stable release indexes.
2. Add newly discovered organizations when they repeatedly produce relevant technical artifacts or materially change the field, regardless of geography or company size.
3. Record why an organization or source was added, which existing source led to it, and whether it remains a candidate, probationary, promoted, or rejected source.
4. Periodically reassess dormant seeds and category gaps. Dormancy is not evidence that a category is complete.

## Eligible artifacts

Admit artifacts with substantive technical content or direct research/developer value:

- model, weight, checkpoint, or capability release
- API or developer tool release with a material new capability
- SDK, compiler, runtime, inference stack, agent framework, or evaluation tool
- benchmark, evaluation suite, leaderboard methodology, or system card
- dataset, data engine, simulator, or environment release
- technical standard, protocol, interoperability specification, or hardware/software interface
- technical report, research preview, system demonstration with inspectable technical evidence, or project page
- important open-source repository or a major version that changes capability, reproducibility, or accessibility
- official paper/proceedings release when the organization page adds evidence not present in bibliographic indexes

Exclude or reject:

- financing, valuation, acquisition, partnership, award, conference-booth, hiring, or executive-personnel news without a technical artifact
- pure marketing copy, teaser countdowns, vague capability claims, reposts, and social posts without a canonical first-party technical destination
- routine product promotions, customer stories, minor UI changes, pricing-only changes, or availability announcements with no material technical change
- third-party rumor, leak, scraped mirror, SEO roundup, or press coverage as the sole evidence
- repository churn, dependency bumps, generated releases, or trivial version tags presented as important research progress

A mixed announcement may be eligible only for its separable technical artifact. Ignore the financing or marketing narrative and link the canonical technical source.

## Official-source priority and evidence

Use sources in this order:

1. Canonical first-party technical page, documentation release note, research page, specification, model card, dataset card, or system card.
2. First-party repository/release under a verified organization, including linked license, weights, code, issue tracker, and tagged version.
3. First-party feed, sitemap, changelog index, or official organization model hub used for discovery.
4. Official social announcement only as a discovery pointer or date corroboration; follow it to the canonical technical artifact.
5. Independent sources only for corroboration, adoption, reproduction, criticism, or missing context. They cannot turn an unofficial artifact into an official release.

For each candidate capture:

- normalized organization and program/lab
- artifact type, canonical artifact identity, title, release/version, and first-party release date
- canonical announcement plus separate repository, model/weight, documentation, API, dataset, benchmark, standard, paper, and license links when applicable
- availability class: public API, downloadable artifact, open-source, open-weights, research-only, gated, commercial-only, preview-only, or unknown
- what materially changed compared with the previous version
- capability and benchmark claims, clearly labeled as first-party claims until independently reproduced
- disclosed architecture, training, data, hardware, safety, usage and licensing constraints
- relevance to configured topics and evidence gaps

An official host proves ownership, not quality. Apply the artifact-specific quality rubric after identity verification.

## Candidate normalization and deduplication

Use a stable `canonical_id` based on the owned artifact, not the announcement headline. Keep release events separate from the persistent entity:

```json
{
  "artifact_type": "sdk",
  "lane": "organization-release",
  "canonical_id": "org-release:<organization>:<artifact>",
  "entity_id": "org-release:<organization>:<artifact>",
  "event_id": "org-release:<organization>:<artifact>@<version-or-date>",
  "organization": "...",
  "program": "...",
  "released_at": "...",
  "official_url": "...",
  "artifact_urls": [],
  "source_provenance": [],
  "discovery_category": "developer-tools-open-platforms"
}
```

Prefer an upstream project/model identifier, tagged version, commit SHA, DOI, standard version, dataset version, or dated release slug. Treat a materially new version as a new event on the same entity. Do not treat page edits, repository `lastModified`, or a new marketing post as a release event without a substantive diff.

When the same model qualifies for `open-model` and `organization-release`, keep one entity and one delivery item. Preserve both lane discoveries in provenance and count it in each lane's retrieval audit, but only once in review and digest totals.

## Safe source promotion

Discovering a URL does not authorize permanent automated scraping. Track each endpoint through `candidate → probation → promoted` or `rejected`. Promote it only when all gates pass:

### Ownership and trust

- Verify first-party ownership through an organization-controlled domain, an official page linking the repository/account, or another auditable ownership chain.
- Require HTTPS and a trusted, non-lookalike host. Reject URL shorteners, user-content mirrors, arbitrary subdomains, and redirect chains that leave the verified ownership boundary.
- Respect authentication boundaries, site terms, robots directives where applicable, and rate limits. Never bypass login, anti-bot, or access controls.

### Stable retrieval contract

- The source exposes a stable index/feed/sitemap/changelog/release API or another bounded enumeration path.
- Entries have canonical permalinks and a reliable published/released date. Record updated time separately.
- Pagination, ordering, and cursor behavior are understood well enough to avoid silent gaps or infinite rescans.
- The parser can distinguish technical releases from marketing, financing, hiring and unrelated posts.

### Bounded operating budget

- Set per-source request, pagination, item, byte, redirect and wall-clock limits before automation.
- Use conditional requests or incremental cursors where supported; cache only public source material.
- Apply timeouts, retry ceilings with backoff, content-type checks, maximum body sizes and a circuit breaker. A failed source must degrade to an audited coverage gap, not stall the entire radar.
- Do not download model weights, datasets, binaries or repository archives during discovery. Fetch only the metadata/evidence authorized by the review task.

### Tests before promotion

- Save representative public fixtures or deterministic response summaries without credentials or personal data.
- Test ownership/host validation, date extraction, canonical identity, pagination/cursor bounds, duplicate handling, exclusion rules, malformed content, empty results and network failure.
- Run the source in probation without affecting seen-state. Compare discovered items with the official index for at least one bounded window.
- Promote only after schema validation and tests pass. Record the test version and promotion time.
- If the layout, ownership, redirect target or parsing contract changes, demote the source to probation automatically until tests pass again.

Never mark a candidate seen during source discovery or probation. Seen-state changes only after the intended final delivery succeeds.

## Per-run coverage audit

Every run must emit a machine-readable audit (for example `organization-release-coverage.json`) and a compact human-readable section in the digest. Absence of release candidates is not a reason to omit the audit.

The audit must include:

### Window and lane state

- exact timezone-aware screening window
- lane state: `completed`, `completed_no_eligible_release`, `partial`, or `failed`
- configured categories and categories intentionally out of scope, with reasons
- request, item and time budgets used versus configured

### Coverage matrix

For each category and organization/source record:

- `success`: source checked and its bounded window completely enumerated
- `partial`: source responded but pagination, truncation, date ambiguity or parser degradation leaves a gap
- `failed`: retrieval or validation failed, with a safe error summary
- `uncovered`: no promoted stable first-party index is currently available, or the source was not reached within the declared budget
- `no_release`: source was successfully covered and contained no eligible release in the window

Do not collapse `no_release` into failure or `uncovered`.

### Source expansion

Report organizations and endpoints newly discovered during the run, their discovery parent, ownership evidence, current promotion state, rejection reason when applicable, and whether they change future coverage.

### Candidate funnel

At minimum report counts for:

1. seed organizations scheduled
2. dynamically expanded organizations scheduled
3. endpoints attempted / succeeded / partial / failed / uncovered
4. raw indexed entries
5. in-window dated entries
6. technically eligible entries after marketing/finance/hiring exclusion
7. normalized unique artifacts and duplicate merges
8. topic-relevant candidates
9. identity/evidence verified candidates
10. reviewed, highlighted, watchlisted, rejected and unreviewed candidates

Name every truncation point and preserve the unscreened count. A digest with unreviewed candidates or partial/failed/uncovered sources is a shortlist, not comprehensive coverage.

## Review and output contract

For every highlighted organization release include:

- organization/program, artifact type, release date/version and canonical first-party URL
- separate artifact, documentation, code/model/data/standard/license links when verified
- what changed and why it matters to the user's research
- technical mechanism or system components at the level actually disclosed
- first-party evaluation claims and any independent evidence, clearly separated
- availability, openness/license class, hardware/API/usage constraints and migration or compatibility risks
- evidence level, unresolved unknowns, limitations and a concrete reason to inspect or use it

Put identity-verified but incompletely evaluated releases in an explicitly labeled release watchlist. Reject promotional artifacts rather than padding the watchlist. End the lane with the coverage matrix summary, source expansion log, candidate funnel and exact screening window.
