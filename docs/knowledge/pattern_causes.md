# Wafer defect patterns: causes associated with them in the literature

Generated from `pattern_causes.json` by `render_pattern_causes.py`; edit the JSON, not this file. The API serves the JSON at `GET /api/v1/knowledge/patterns`.

## How to read it

These are hypotheses to check, not diagnoses. Each row is a cause that open-access papers associate with a WM-811K defect pattern, quoted exactly with its location. The papers state these links briefly, mostly by citing older work; none was tested on this fab's data, and no source read gives direct experimental evidence for a pattern-to-cause link. Confidence rates the support in the literature read: medium = stated by two or more papers that cite different earlier sources; low = stated by one paper, or by an unreviewed preprint without a citation. High is not used.

Every quote was read on the publisher's or arXiv's page on 2026-10-14 and kept only when two separate reads returned the same words. Quotes are short spans of longer sentences. Source details and licences are in [README.md](README.md).

## Patterns

### Center

- **Associated in several papers with problems in thin-film deposition (one adds the plasma area).** Evidence: medium.
  - "Center and Edge-Ring are caused by thin film deposition and etching problems, respectively" (Zheng et al., 2021; Section 1, Introduction (citing refs. 4 and 5: Piao et al. 2018; Jin et al. 2019))
  - "A center often arises due to problems in the thin film deposition" (Chen et al., 2023; Section 1, Introduction (citing Wang and Bensmail 2006))
  - "the center type has the effect of problems in the plasma area or thin-film deposition" (Jeong et al., 2023; Experiment, Data description (citing ref. 28: Hansen and Thyregod 1998))
- **Associated in one paper with uneven mechanical polishing or abnormal liquid pressure.** Evidence: low.
  - "For example, the Center pattern means that the mechanical polishing is uneven, or the pressure of the liquid is abnormal." (Xu et al., 2022; Section 1, Introduction (no citation))
- **A circular, center-located pattern is associated in one paper with chemical stains or mechanical equipment faults.** Evidence: low.
  - "often corresponds to chemical stains or mechanical equipment faults" (Ezzat et al., 2021; I. Introduction, about a circular-shaped, center-located pattern (citing refs. 2 and 3))

### Donut

- **A center-located donut pattern is associated in one paper with possible tooling problems.** Evidence: low.
  - "is routinely observed in wafer data due to possible tooling problems" (Ezzat et al., 2021; I. Introduction, about a center-located, donut-shaped pattern (citing ref. 5))

### Edge-Loc

- **Associated in one paper with uneven heating during the diffusion process.** Evidence: low.
  - "the edge-loc type has the same effect as uneven heating during the diffusion process." (Jeong et al., 2023; Experiment, Data description (sentence citing ref. 28: Hansen and Thyregod 1998))
- **A zone-shaped, edge-located pattern (closest to Edge-Loc) is associated in one paper with uneven polishing or edge-die effects.** Evidence: low.
  - "can be traced to uneven polishing or edge-die effects" (Ezzat et al., 2021; I. Introduction, about a zone-shaped, edge-located pattern (citing ref. 4))

### Edge-Ring

- **Associated in two papers with problems in the etching step.** Evidence: medium.
  - "Center and Edge-Ring are caused by thin film deposition and etching problems, respectively" (Zheng et al., 2021; Section 1, Introduction (citing refs. 4 and 5: Piao et al. 2018; Jin et al. 2019))
  - "a ring is due to problems in the etching step" (Chen et al., 2023; Section 1, Introduction (citing Wang and Bensmail 2006))
- **Associated in one paper with abnormal temperature control during annealing.** Evidence: low.
  - "Abnormal temperature control during annealing may lead to an Edge-Ring pattern." (Xu et al., 2022; Section 1, Introduction (no citation))

### Loc

- **Associated, in one unreviewed preprint and without a citation, with localized contamination or particles.** Evidence: low.
  - "often resulting from localized contamination or particle interference." (Nath, 2025; Section III.A, Data Collection, item V (Local); no citation)

### Near-full

- **Associated, in one unreviewed preprint and without a citation, with major process malfunctions or equipment failures.** Evidence: low.
  - "typically signifying major process malfunctions or equipment failures." (Nath, 2025; Section III.A, Data Collection, item VI (Near-Full); no citation)

### Random

- **Randomly scattered failing dies are associated in two papers with ordinary process variation or a poorly controlled process environment, not with one assignable source.** Evidence: medium.
  - "since they are merely artifacts of random process variation." (Ezzat et al., 2021; I. Introduction, about randomly scattered defective chips)
  - "is often due to a lack of process environment management or factors that are difficult to control directly." (Kim, 2024; Section 3.2, Random Noise Filtering and Data Augmentation (about random noise, not the Random class))

### Scratch

- **Associated in several papers with wafer handling by machines, or with the moving or cutting steps.** Evidence: medium.
  - "Scratch is caused by machine handling" (Zheng et al., 2021; Section 1, Introduction (citing refs. 4 and 5: Piao et al. 2018; Jin et al. 2019))
  - "a scratch is a result of machine handing problems" (Chen et al., 2023; Section 1, Introduction (citing Wang and Bensmail 2006); "handing" is as printed)
  - "The Scratch pattern indicates an exception in the moving or cutting processes." (Xu et al., 2022; Section 1, Introduction (no citation))

## Sources

- `zheng2021`: Huilin Zheng, Syed Waseem Abbas Sherazi, Sang Hyeok Son, Jong Yun Lee. *A Deep Convolutional Neural Network-Based Multi-Class Image Classification for Automatic Wafer Map Failure Recognition in Semiconductor Manufacturing*. Applied Sciences 11(20), 9769, 2021. https://doi.org/10.3390/app11209769
- `xu2022`: Qiao Xu, Naigong Yu, Firdaous Essaf. *Improved Wafer Map Inspection Using Attention Mechanism and Cosine Normalization*. Machines 10(2), 146, 2022. https://doi.org/10.3390/machines10020146
- `jeong2023`: Iljoo Jeong, Soo Young Lee, Keonhyeok Park, Iljeok Kim, Hyunsuk Huh, Seungchul Lee. *Wafer map failure pattern classification using geometric transformation-invariant convolutional neural network*. Scientific Reports 13, 8127, 2023. https://doi.org/10.1038/s41598-023-34147-2
- `chen2023`: Yu Chen, Meng Zhao, Zhenyu Xu, Kaiyue Li, Jing Ji. *Wafer defect recognition method based on multi-scale feature fusion*. Frontiers in Neuroscience 17, 1202985, 2023. https://doi.org/10.3389/fnins.2023.1202985
- `kim2024`: Moo Hyun Kim, Tae Seon Kim. *Development of a Wafer Defect Pattern Classifier Using Polar Coordinate System Transformed Inputs and Convolutional Neural Networks*. Electronics 13(7), 1360, 2024. https://doi.org/10.3390/electronics13071360
- `ezzat2020`: Ahmed Aziz Ezzat, Sheng Liu, Dorit S. Hochbaum, Yu Ding. *A Graph-Theoretic Approach for Spatial Filtering and Its Impact on Mixed-type Spatial Pattern Recognition in Wafer Bin Maps*. arXiv:2006.13824 (v4); the arXiv page lists the journal DOI 10.1109/TSM.2021.3062943 (IEEE Transactions on Semiconductor Manufacturing), 2021. https://arxiv.org/abs/2006.13824
- `nath2025`: Sushmita Nath. *A Comparative Analysis of Semiconductor Wafer Map Defect Detection with Image Transformer*. arXiv:2512.11977 (v1), preprint, not peer reviewed, 2025. https://arxiv.org/abs/2512.11977
