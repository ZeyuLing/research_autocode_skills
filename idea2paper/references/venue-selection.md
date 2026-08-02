# Venue Selection and Template Policy

Apply this policy when the user does not supply a venue or when a supplied venue needs rule verification.

## Candidate construction

1. Extract field, task, method, modality, application, and paper-type tags from the current idea.
2. Start from `venue-registry.json`. It is the strict default pool, not a source for live deadlines.
3. Automatic selection may consider only ECCV, ICCV, CVPR, NeurIPS (including the NIPS alias), ICML, ICLR, AAAI, IJCAI, ACM MM (including the ACMMM alias), ACL, and EMNLP.
4. Reject every pool-external venue during automatic selection, even when a community-standing URL is supplied. Do not auto-add domain-specific conferences.
5. Exclude workshops by default unless the user explicitly requests one.
6. Give each candidate a `scope_fit` score from 1 to 5 and a one-sentence fit rationale.

If the user explicitly names a venue outside the pool, it may be retained with
`selection_mode=user_specified` after verifying its rules. Do not describe that
choice as an automatically selected top-pool venue, and do not let it expand the
default registry.

## Eligibility and ranking

A venue is eligible only when:

- the canonical venue or a registered alias is present in the strict default pool;
- `tier` is `flagship` or `top` as assigned by the registry;
- `scope_fit >= 4`;
- an official CFP or submission page was checked;
- the abstract deadline has not passed; or, when no separate abstract deadline exists, the full-paper deadline has not passed;
- `has_separate_abstract_deadline=false` is valid only when `abstract_deadline` is empty; contradictory candidates are rejected.

Rank eligible venues deterministically by:

1. effective deadline ascending;
2. scope fit descending;
3. tier (`flagship` before `top`);
4. venue name for a stable tie break.

Do not include experiment duration, available compute, author schedule, or estimated completion time in venue eligibility or ranking.

Interpret AoE as UTC-12. Store deadlines as timezone-aware ISO 8601 timestamps. Never compare naive local times.

## Required evidence

For every retained candidate, record:

```json
{
  "name": "ExampleConf",
  "edition": "2027",
  "track": "main",
  "tier": "flagship",
  "scope_fit": 5,
  "fit_reason": "...",
  "idea_version": "idea_v2",
  "idea_tags": ["task", "modality", "method"],
  "scope_evidence_url": "https://official.example/call-for-papers",
  "has_separate_abstract_deadline": true,
  "abstract_deadline": "2026-09-01T23:59:59-12:00",
  "paper_deadline": "2026-09-08T23:59:59-12:00",
  "deadline_status": "confirmed",
  "official_url": "https://...",
  "deadline_source_url": "https://official.example/dates",
  "template_url": "https://...",
  "checked_at": "2026-08-01T10:00:00Z",
  "template_checked_at": "2026-08-01T10:00:00Z",
  "template_status": "current_cycle",
  "template_path": "venue/template/author-kit.zip",
  "template_sha256": "<64 lowercase hex characters>",
  "template_required_tokens": ["\\usepackage{exampleconf_2027}"],
  "anonymity": "double_blind",
  "ai_disclosure_policy": "...",
  "page_rules": {
    "main_text_pages": 8,
    "references_counted": false,
    "appendix_policy": "...",
    "supplement_policy": "..."
  }
}
```

Also capture page limit, whether references count, anonymity, supplement rules, author-registration rules, dual-submission policy, ethics/reproducibility checklists, and AI-use disclosure.

Prefer official CFP, author-kit, submission-system, proceedings, and policy pages over aggregators. Treat unofficial deadline sites only as discovery leads.

`deadline_status`, `has_separate_abstract_deadline`, `idea_version`,
`idea_tags`, `fit_reason`, `scope_evidence_url`, `deadline_source_url`, and
`checked_at` are mandatory for every automatic candidate. Recheck official
sources within 24 hours of automatic selection.

## Unknown future cycles

If no suitable venue has a confirmed future deadline, choose the best-fit next cycle only as `tentative`. Do not present a previous-year date as current. Save the previous cycle's official evidence and add a deadline-refresh task outside the paper.

If an edition's abstract deadline is known to have passed, never select that edition even when the full-paper deadline is open.

## Template policy

1. Download only an official author kit or official repository release.
2. Record URL, edition, checked time, and a file hash.
3. Do not enable shell escape or execute untrusted template scripts.
4. Save the downloaded kit under `venue/template/`, record its SHA-256 hash, and record one or more exact template signature tokens that must appear in `paper/main.tex`.
5. Use the current edition when available.
6. Otherwise use the previous official edition, set `template_status=previous_cycle`, and add `\TemplateTODO{TEMPLATE-UPDATE}{...}` with an adjacent TODO in `main.tex`.
7. When the current template appears, invalidate venue layout only, migrate the source, recompile, and recheck page count, anonymity, teaser placement, fonts, and references.

## Page budget

When migrating into the official template, keep the sole Conclusion input and optional Limitations input before `idea2paper:end-body`. If a venue-exempt AI disclosure follows, put `idea2paper:end-exempt` immediately after that one input; otherwise place the two labels together. Put `idea2paper:end-references` immediately after the bibliography and begin `appendix/appendix.tex` with `\appendix`. The compile gate binds this canonical order to the real section/bibliography/appendix commands, caps the exempt disclosure to one additional page, and uses the appropriate body label according to whether references count.

Create a budget immediately after venue lock. Reserve space for the overview, main tables, and teaser before prose expansion. The sketch may exceed the official body limit by at most one page; `SUBMISSION_READY` may not exceed it at all.
