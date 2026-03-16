# Rebuttal Writing Guide

Compiled from Devi Parikh's rebuttal guide and SIGGRAPH rebuttal guidelines.

## Strategic Overview

### Before You Write

1. **Copy all reviews into a single document.** Break down each review into specific action items. Track which reviewer (R1, R2, etc.) raised each point. Group similar concerns across reviewers.

2. **Identify key concerns per reviewer.** Each reviewer typically has 1-2 core points they truly care about — these are usually stated in their justification. Even if a reviewer writes many paragraphs, they won't remember all of it. But they will remember those 1-2 key points vividly.

3. **Understand why they gave that score.** The score reflects the reviewer's overall impression. Your rebuttal must address the root cause of that impression, not just the surface-level complaints.

### Writing the Rebuttal

#### Structure

1. **Opening** (optional): If there's a global misunderstanding shared across reviewers, address it upfront in 1-2 sentences directed at all reviewers.

2. **Per-reviewer responses**: Address each reviewer's concerns in order. Use clear section headers that describe the concern — reviewers should be able to skim headers and find their questions.

3. **Group similar concerns**: If R1 and R3 both worry about generalization, write one response and reference it from both: "Generalization to unseen scenes (R1/R3)".

#### Per-Response Structure

Each response should follow this pattern:

```
### [R{N}-W{M}] Concern title (paraphrased concisely)

[1-2 sentence direct answer]

[Supporting evidence/explanation if needed]

[If applicable: "We will add this clarification to Section X in the revised version."]
```

The first sentence is the most important — it should directly answer the question or address the concern. Don't build up to your answer.

### Tone

- **Professional and respectful**, like a Q&A at a conference
- **Never condescending**, even when the reviewer misunderstood
- **Don't argue** about whether a request is reasonable — just provide what they ask for
- When the reviewer is factually wrong: "We appreciate this question. To clarify, [correct information with citation/evidence]..."
- When you can't fully address a concern: acknowledge it honestly and explain what you can do

### Common Pitfalls

1. **Introducing new information that opens new attack surfaces.** Every new claim is a potential weakness. Only provide what's needed to address the concern.

2. **Being defensive.** Phrases like "We strongly disagree" or "The reviewer failed to understand" are counterproductive. Stay neutral and evidence-based.

3. **Promising things you can't deliver.** If you commit to adding experiments in the camera-ready, you must deliver. Broken promises can lead to rejection during shepherding.

4. **Ignoring minor points.** Even if a point seems trivial, briefly acknowledge it. Unanswered points signal that you either didn't read carefully or couldn't address them.

5. **Over-paraphrasing reviewer comments.** Don't recharacterize what the reviewer said — it can feel like you're putting words in their mouth. Quote them briefly if needed, then respond.

## Response Templates by Weakness Category

### Insufficient Contribution

The key is to demonstrate that the work provides genuine new insights or capabilities that the community didn't have before.

Strategies:
- Highlight the specific technical novelty and why it's non-obvious
- Show that existing approaches can't achieve the same result (with evidence)
- Point to downstream applications or impact
- If the approach seems "straightforward", explain the insight that made it work (often the insight is the contribution, not the implementation)

### Unclear Writing

Acknowledge, fix, and show you've fixed it.

Strategies:
- Thank the reviewer for identifying the unclear part
- Provide the clarification directly in the rebuttal
- Commit to revising the specific section: "We will revise Section X.Y to include..."
- If motivation is questioned, provide the motivation concisely here

### Weak Experimental Results

Show that your results are meaningful in context.

Strategies:
- If improvements are small: explain why even small improvements matter in this domain (e.g., saturated benchmarks, practical significance)
- Provide additional metrics or evaluation angles that tell a more complete story
- If possible, add new experiments that strengthen the case
- Compare on additional datasets or settings

### Method Design Flaws

Address the specific technical concern head-on.

Strategies:
- If the setting is questioned: justify with real-world use cases or prior work
- If there's a technical flaw: explain why it's actually correct (with equations/theory if needed), or acknowledge and propose a fix
- For robustness concerns: show results across multiple settings/hyperparameters
- For limitation concerns: explicitly compare benefits vs. limitations and explain the net positive

### Insufficient Evaluation

Provide the missing evidence.

Strategies:
- Add requested ablation studies (if feasible within rebuttal period)
- Add missing baselines with results
- Add the missing metric and report numbers
- If data seems too simple: test on harder data or explain why the data is appropriate

## Final Checklist

After writing the complete rebuttal:

- [ ] Each reviewer's key concern (from justification) has a clear, direct answer
- [ ] No response introduces claims that could create new weaknesses
- [ ] All commitments for camera-ready are achievable
- [ ] Responses are self-contained (reader doesn't need to re-read the review)
- [ ] Tone is consistently professional and non-confrontational
- [ ] All reviewer points are addressed (even minor ones get a brief acknowledgment)
- [ ] Have a colleague read through to check if the key concerns are convincingly addressed
