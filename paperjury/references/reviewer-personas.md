# Holistic reviewers and meta reviewer

Conference REVIEW roles are different from optional legacy local-context jurors.

## Shared responsibility

Every reviewer reads the full paper and supplied appendix, figures, tables and
references. Each evaluates motivation, related work, soundness, empirical support,
contribution, significance, clarity, reproducibility, limitations and ethics.
Do not allocate sections or forbid reviewing dimensions.

Report real strengths and decision-relevant weaknesses. Avoid a universally
hostile gatekeeper persona, issue quotas, forced disagreement and outcome bias.

## Background diversity that changes judgment

Give the panel different research experience and defensible ways of weighing
evidence, not merely different job titles. Select profiles from the topic and
contribution types before seeing any reviewer output. Do not derive profiles from
suspected flaws, preferred verdicts or author wishes. All use the same venue
standard; none is assigned an easier/harder acceptance threshold. A professor is
not automatically harsher, and an early-career researcher is not automatically
focused on leaderboard gains. Do not impersonate real scholars.

Write an external `panel.json` with a `reviewers` array. Each card has exactly:

- `reviewer_id`: the roster identity, e.g. `R1`.
- `background`: a plausible field, career context and relevant experience.
- `contribution_lens`: what kinds of scientific value this experience helps assess.
- `evidence_lens`: evidence this reviewer knows how to interpret and its limits.
- `uncertainty_policy`: how they distinguish an unanswered question from evidence
  against a central claim, and how uncertainty affects confidence versus rating.
- `scope_policy`: how they assess a narrower valid contribution and wider claims.
- `counterweight`: what evidence can overcome this lens's initial concern or
  limit its preferred kind of contribution.

Select complementary combinations; do not copy these examples as a fixed panel:

| Experience | Contribution/evidence priorities | Counterweight |
|---|---|---|
| Builds methods and analyzes mechanisms | Explanatory value, distinct mechanism and isolating comparisons; a well-supported conceptual advance may matter without the highest headline metric | A novel explanation needs evidence and useful scope; novelty alone is insufficient |
| Reproduces results and designs empirical comparisons | Credible effect sizes, fair controls and useful empirical discoveries; familiar components may still yield a contribution | Judge evidence needed for the stated claims, not an unlimited checklist of additional experiments |
| Works between the main field and an adjacent application or systems area | Problem importance, transfer and demonstrated cost/quality tradeoffs; bounded gains can have material value | Practical relevance does not excuse invalid comparisons or claims beyond the tested setting |

Each card must describe a coherent researcher who can recommend acceptance or
rejection on the evidence. Vary more than one substantive axis between each pair;
the helper rejects exact duplicated lenses, but semantic diversity requires the
orchestrator's judgment. Expertise never excuses incomplete reading. Do not
include target ratings, numerical weights, a desired mean/variance, an advocate
or opponent assignment, or instructions to disagree. No reviewer sees other cards.

Freeze profile digests in `prepare --panel panel.json`; keep the full panel file
outside the paper packet. `assessment-prompt ... PROFILE_JSON ...` accepts the
individual card only if its digest matches that round. The initial assessment
contains no rating or acceptance decision. In the later score pass, retain its
findings and give a short, evidence-linked decision explanation: which factors
dominate, which weaknesses are bounded, and why the chosen label fits better
than its adjacent available labels. Do not invent a weakness to fill a form.

Independent contexts on one model can still share biases. Different identities
do not establish independent model populations, calibrated score probabilities,
or human-reviewer variance. Record the actual execution setup if known. Do not
change models, invent random reviewer biases, perturb ratings, or keep sampling
until a spread appears. Genuine agreement is an acceptable outcome.

## Meta reviewer

A separate fresh agent, not the parent and not a panel reviewer, reads the whole
packet and every raw review. They decide which arguments matter, check whether
concerns are supported or answered elsewhere, and explain disagreements. Neither
reviewer confidence nor numerical majority substitutes for evidence.

The meta reviewer alone owns final recommendation, justified final score and
ordered priorities. Where the venue has no meta numeric score, label it a
simulation summary. Do not invent a rebuttal, panel discussion or consensus.
They may request clarification from a reviewer; the parent only transports the
question and raw answer, without adding author-side facts.

When ratings match, compare the decisive evidence and tradeoffs before calling
it consensus. Reviewers may agree on a label while disagreeing about novelty,
scope or the decisive experiment. Treat the panel diagnostic as a process signal,
not scientific evidence or a reason to alter scores.

## Coverage

Record pages read, sections considered, material figures/tables inspected and
access limitations. Written emphasis may differ while reading remains complete.
A thumbnail is not a table inspection; a quote is not proof of comprehension.
Confidence reflects actual assessment ability and access, not a default high score.
