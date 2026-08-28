# Chinese degree-thesis review policy hierarchy

Last researched: 2026-08-14. Verify later revisions before relying on this file for a real submission.

## Rule hierarchy

Use this order of authority:

1. current law and binding national regulations;
2. current degree-granting institution rules;
3. school/department implementation rules and the official thesis template;
4. current recommended national standards when the institution has not specified a conflicting local form;
5. review customs and this skill's stricter simulated panel.

Never infer a local pass/fail rule from another university. Use other institutions only to understand common practice or to design a conservative simulation.

The A/B/C/D defense recommendations in `grading-and-verdicts.md` are the skill's explicit fallback simulation when no verified institutional category scheme is available. They are not national statutory grades. When a current institution or school form defines different letters, wording, or consequences, that verified form controls and must be cited in every report.

## National law

The **Academic Degrees Law of the People's Republic of China** took effect on 2025-01-01.

- Article 25 requires degree-granting institutions to send a master's or doctoral thesis/practical achievement to experts before organizing the defense. A candidate proceeds only when the expert review satisfies institutional rules.
- Article 26 sets defense-committee minima: at least three members for a master's defense and at least five for a doctoral defense, with at least two external members on a doctoral committee.

These committee numbers are not statutory counts for blind or external thesis reviewers.

Official source: National People's Congress, <https://www.npc.gov.cn/npc/c2/c30834/202404/t20240426_436840.html>

## National post-award sampling is a different process

The 2014 **Measures for Sampling Inspection of Doctoral and Master's Dissertations** concern theses from the previous academic year after degrees have been awarded.

- doctoral sampling is about 10 percent and master's sampling about 5 percent;
- each sampled thesis is sent to three peer experts;
- two or more `unqualified` opinions identify a problematic thesis;
- one `unqualified` opinion triggers review by two additional experts, and one or more negative opinions in that second round identify a problematic thesis;
- experts must complete reviews independently and objectively.

Do not transplant this `3 + possible 2` process into a university's pre-defense rules.

Official source: State Council Academic Degrees Committee and Ministry of Education, <https://www.moe.gov.cn/srcsite/A22/s7065/201402/t20140212_165556.html>

## National evaluation dimensions

The Ministry of Education described four top-level indicators used to develop doctoral dissertation evaluation elements:

1. topic selection;
2. innovation and thesis value;
3. foundational knowledge and research capability;
4. thesis standardization.

The reply notes twelve underlying elements differentiated by academic/professional degree and broad discipline class. Use the four indicators as an organizing spine, not as permission to invent unavailable official sub-scores.

Official source: Ministry of Education reply to CPPCC Proposal No. 3131, <https://www.moe.gov.cn/jyb_xxgk/xxgk_jyta/jyta_ddb/201901/t20190117_367244.html>

## Institutional reviewer counts vary

Examples demonstrate why reviewer counts must be sourced locally:

- A published Zhejiang University rule requires at least five doctoral reviewers, at least four external, and at least three doctoral supervisors; it requires at least three master's reviewers, with at least one external. This public document is old and must be checked against the current school/department rule before operational use: <https://polymer.zju.edu.cn/2009/0521/c38015a1578732/page.htm>
- A 2025 Beihang school rule describes five to seven doctoral reviewers and changing minimum blind-review counts by cohort: <https://www.ee.buaa.edu.cn/info/1036/19610.htm>
- A Northeast Agricultural University rule uses at least five doctoral and at least three full-time master's reviewers, but divides blind and non-blind review differently: <https://graduate.neau.edu.cn/info/1029/2208_1.htm>

Therefore this skill's five-reviewer doctoral panel and three-reviewer master's panel are **strict simulation defaults**, not universal national legal requirements. Override them only when the user requests another panel or a verified institutional rule requires a different process.

## CS/AI implementation example

Tongji University's School of Computer Science and Technology published a 2025 evaluation scheme organized around:

- topic and literature review;
- innovation and thesis value/application value;
- theoretical foundation plus research/practical capability;
- academic norms and writing quality.

Its academic doctoral form gives innovation and thesis value greater weight and treats a low innovation subscore as a failing condition. Use this only as a CS-specific example unless Tongji is the target institution.

Official school page and forms: <https://cs.tongji.edu.cn/info/1037/3502.htm>

## Current national standards

As of the research date:

- **GB/T 7713.1-2025**, *Information and documentation—Presentation of documentation—Part 1: Theses and dissertations*, took effect on 2026-02-01 and replaced GB/T 7713.1-2006: <https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=36C05B5738C54D42B4B262525320B52F>
- **GB/T 7714-2025**, *Information and documentation—Rules for bibliographic references and citations to information resources*, took effect on 2026-07-01 and replaced GB/T 7714-2015: <https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=C6CE52E55AC09B9C79A20AEA77CEDD14>

Both are recommended national standards. The institution's current template and implementation rules remain the operational authority for local submission format.

## Blind-copy checks

When a blind-review copy is required, verify the exact institutional instructions. Common items to inspect include:

- author and supervisor names, student number, signatures, and contact details;
- acknowledgments;
- CV, publication list, project identifiers, grant wording, and self-citations that directly reveal identity;
- PDF metadata, filenames, embedded comments, tracked changes, repository links, and figure watermarks;
- school, department, laboratory, company, employer, partner organization, and institutional identifiers that the school explicitly requires removed;
- proprietary project or dataset descriptions, work-experience wording, affiliations in publication records, and combinations of otherwise indirect clues that can identify the candidate.

Audit the complete submitted blind-review artifact, including body text, captions, tables, acknowledgments, CV/publications, data descriptions, footnotes, URLs, PDF metadata, filenames, comments, and figure watermarks. An ordinary author copy may legitimately display the author's name, student number, supervisor, and institution; do not classify those fields as thesis defects merely because a source-level `BlindReview` switch would not hide them. If the institution creates or transforms the blind copy at submission, inspect that generated copy instead of inferring anonymity from the author-copy template.

Do not automatically delete every self-citation. Preserve scientific traceability while following the institution's prescribed anonymization method.

## Policy evidence record

For every invoked rule, record:

| Field | Required value |
|---|---|
| Jurisdiction | national / institution / school / department |
| Document | exact title |
| Issuer | issuing body |
| Version | publication, revision, and effective date |
| Provision | article, section, or form item |
| Source | official URL or supplied local file |
| Status | verified current / historical / unverified |
| Effect | what the rule changes in this review |

If a rule is historical or unverified, it cannot by itself create an `S0` or institutional fail conclusion.

## Skill provenance

The workflow was designed after reviewing the MIT-licensed [Agents365-ai/thesis-reviewer](https://github.com/Agents365-ai/thesis-reviewer). It retains useful ideas such as separating general and CS-specific checks, performing chapter and cross-chapter review, and generating a structured revision roadmap. This implementation is independently written and adds current national standards, policy-level separation, clean-room 5/3 reviewer panels, rendered-PDF inspection, evidence adjudication, remedy classes, and independent re-review.
