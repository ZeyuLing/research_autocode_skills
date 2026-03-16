# Rebuttal Draft

We sincerely thank all reviewers for their valuable and constructive feedback. We address each concern below.

---

## Response to Reviewer 1

We thank Reviewer 1 for the detailed evaluation.

### [R1-W1] Novelty of combining NeRF and diffusion model

We respectfully clarify that our method is not a straightforward combination of NeRF and diffusion model. While both components are individually well-studied, the key technical contribution of our work lies in [**TODO: describe the specific non-trivial insight, e.g., the novel conditioning mechanism / the joint training strategy / the specific architectural design that enables X**]. To our knowledge, existing works that integrate NeRF and diffusion models [cite relevant prior works] differ from ours in the following critical aspects:

1. [**TODO: Difference 1 — e.g., prior works use diffusion for 2D generation and lift to 3D, whereas we directly operate in the radiance field space**]
2. [**TODO: Difference 2 — e.g., our approach introduces a novel loss function / sampling strategy that is essential for convergence**]
3. [**TODO: Difference 3 — e.g., we enable a new capability (such as X) that previous integrations cannot achieve**]

We will add a more detailed discussion of these distinctions in the related work section of the revised manuscript.

### [R1-W2] Experiments only on synthetic datasets

We acknowledge this concern. We chose synthetic datasets for the initial evaluation because they provide ground-truth geometry and appearance, enabling precise quantitative analysis. However, we agree that real-world validation is important. We have now conducted additional experiments on [**TODO: specify real-world dataset, e.g., Mip-NeRF 360 / Tanks and Temples / ScanNet**], and the results are shown below:

| Method | PSNR | SSIM | LPIPS |
|--------|------|------|-------|
| Baseline | [TODO] | [TODO] | [TODO] |
| Ours | [TODO] | [TODO] | [TODO] |

[**TODO: briefly describe the real-world results and how they support the paper's claims**]

We will include these results in the revised version.

---

## Response to Reviewer 2

We thank Reviewer 2 for the positive assessment and the constructive suggestions.

### [R2-W1] Missing comparison with Method-X (CVPR 2025)

We thank the reviewer for pointing out this recent work. We have now added a comparison with Method-X. The results are as follows:

| Method | PSNR | SSIM | LPIPS |
|--------|------|------|-------|
| Method-X (CVPR 2025) | [TODO] | [TODO] | [TODO] |
| Ours | [TODO] | [TODO] | [TODO] |

[**TODO: describe the comparison results — if your method outperforms, state by how much and on which metrics; if it underperforms on some metrics, explain the trade-offs, e.g., your method achieves better visual quality at lower computational cost**]

We will add this comparison to Table [X] in the revised paper.

### [R2-W2] Insufficient ablation study

We appreciate this feedback. We have now conducted a complete ablation study covering all three major modules:

| Configuration | PSNR | SSIM | LPIPS |
|--------------|------|------|-------|
| Full model | [TODO] | [TODO] | [TODO] |
| w/o Module A | [TODO] | [TODO] | [TODO] |
| w/o Module B | [TODO] | [TODO] | [TODO] |
| w/o Module C | [TODO] | [TODO] | [TODO] |

[**TODO: briefly analyze the ablation results — which module contributes the most, what does each module bring, are there interactions between modules**]

These results confirm that each module contributes meaningfully to the overall performance. We will include the full ablation table in the revised manuscript.

---

## Response to Reviewer 3

We thank Reviewer 3 for the thorough review and the high-confidence assessment.

### [R3-W1] Static scene assumption is unrealistic

We understand the concern regarding the static scene assumption. We would like to clarify our rationale:

1. **Many important real-world applications involve static scenes.** Indoor scene reconstruction (e.g., real estate, architectural design), cultural heritage preservation, and object-level reconstruction all naturally satisfy the static assumption. These represent a significant and practical application domain.

2. **The static assumption is a common and accepted setting in the NeRF literature.** Foundational works including NeRF [Mildenhall et al., 2020], Mip-NeRF [Barron et al., 2021], Instant-NGP [Muller et al., 2022], and 3D Gaussian Splatting [Kerbl et al., 2023] all operate under this assumption while making substantial contributions.

3. **Our method's core contribution is orthogonal to the static/dynamic distinction.** The proposed [**TODO: name of key technique**] can potentially be extended to dynamic settings by incorporating temporal modeling (e.g., deformation fields), which we consider a promising direction for future work.

We will add a more explicit discussion of the applicability scope and future extensions in the revised paper.

### [R3-W2] Marginal improvement of 0.5dB PSNR over baseline

We appreciate this concern. We would like to provide additional context:

1. **PSNR improvements should be interpreted in the context of the benchmark.** On the [**TODO: dataset name**] benchmark, the gap between recent state-of-the-art methods is typically within 0.3-0.8 dB. Our 0.5 dB improvement is consistent with or exceeds the improvements reported by recent accepted papers in this area, including [**TODO: cite 2-3 recent papers and their reported improvements**].

2. **PSNR alone does not capture the full picture.** Our method also achieves improvements on perceptual metrics: [**TODO: e.g., SSIM improves by X, LPIPS improves by Y**]. Qualitative comparisons (Figure [X] in the paper) show that our method produces [**TODO: describe specific visual improvements, e.g., sharper edges, fewer artifacts in specular regions, better fine-grained details**].

3. [**TODO (optional): If applicable — our method provides additional benefits beyond reconstruction quality, such as faster rendering speed / lower memory footprint / better generalization, which are not captured by PSNR alone.**]

---

## Summary of Revisions

Based on the reviewers' feedback, we commit to the following revisions in the camera-ready version:

1. **Additional experiments on real-world datasets** (R1-W2)
2. **Comparison with Method-X** (R2-W1)
3. **Complete ablation study for all three modules** (R2-W2)
4. **Expanded discussion of the static scene assumption and applicability** (R3-W1)
5. **Enhanced related work section with clearer differentiation from prior NeRF+diffusion methods** (R1-W1)

We believe these revisions will substantially strengthen the paper and address all the reviewers' concerns. We welcome further discussion during the rebuttal period.
