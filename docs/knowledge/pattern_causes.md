# Wafer defect patterns: causes proposed in the literature

These are **hypotheses to check**, not diagnoses. Each row is something an open-access paper says, quoted exactly, with where it says it. The API serves the same content from `pattern_causes.json` (`GET /api/v1/knowledge/patterns`), and the chat's literature search returns these quotes.

## How to read it

Causes proposed in open-access papers, each quoted exactly with its location. They are hypotheses for an engineer to check against this fab's own process history, not diagnoses: the papers state them briefly, often by citing older work, and none was established on this data. No open-access source read for this table states a cause for the Loc or Near-full patterns.

Confidence is a judgement about the support in the literature read, not about this fab:

- **medium**: two or more independent papers agree.
- **low**: one paper states it, briefly or by citing older work.
- **high** is not used: no source read gives direct experimental evidence for a pattern-to-cause link.

How the quotes were collected (2026-10-14): papers were found by web search and read on the publisher's or arXiv's page. A quote was kept only when the same exact words were returned on two separate reads of the page. Quotes are short spans (at most 125 characters) of longer sentences. Several papers cite older work for these statements (noted in the location). The original WM-811K paper (Wu, Jang and Chen, IEEE Transactions on Semiconductor Manufacturing, 2015) is not open access and was not used.

## Patterns

### Center

- **Associated in the literature with thin-film deposition, plasma or etching problems.** Confidence: medium.
  - "Scratch is caused by machine handling, while Center and Edge-Ring are caused by thin film deposition and etching problems" (Zheng et al., 2021; 1. Introduction (citing refs. 4 and 5))
  - "For example, the center type has the effect of problems in the plasma area or thin-film deposition," (Jeong et al., 2023; Results and discussion, Experiment, Data description (citing Hansen and Thyregod 1998, ref. 28))
- **Associated with uneven mechanical polishing or abnormal liquid pressure.** Confidence: low.
  - "For example, the Center pattern means that the mechanical polishing is uneven, or the pressure of the liquid is abnormal." (Xu et al., 2022; 1. Introduction)
- **A circular, center-located pattern is associated with chemical stains or mechanical equipment faults.** Confidence: low.
  - "often corresponds to chemical stains or mechanical equipment faults" (Ezzat et al., 2020; I. Introduction (circular-shaped, center-located defect pattern))

### Donut

- **A center-located donut pattern is associated with possible tooling problems.** Confidence: low.
  - "is routinely observed in wafer data due to possible tooling problems" (Ezzat et al., 2020; I. Introduction (center-located, donut-shaped defect pattern))

### Edge-Loc

- **Associated with uneven heating during the diffusion process.** Confidence: low.
  - "and the edge-loc type has the same effect as uneven heating during the diffusion process." (Jeong et al., 2023; Results and discussion, Experiment, Data description (citing Hansen and Thyregod 1998, ref. 28))
- **A zone-shaped, edge-located pattern is associated with uneven polishing or edge-die effects (the source describes an edge zone, which corresponds most closely to Edge-Loc).** Confidence: low.
  - "can be traced to uneven polishing or edge-die effects" (Ezzat et al., 2020; I. Introduction (zone-shaped, edge-located defect pattern))

### Edge-Ring

- **Associated in the literature with etching or thin-film deposition problems.** Confidence: low.
  - "Scratch is caused by machine handling, while Center and Edge-Ring are caused by thin film deposition and etching problems" (Zheng et al., 2021; 1. Introduction (citing refs. 4 and 5))
- **Associated with abnormal temperature control during annealing.** Confidence: low.
  - "Abnormal temperature control during annealing may lead to an Edge-Ring pattern." (Xu et al., 2022; 1. Introduction)

### Loc

No open-access source read states a cause for this pattern.

### Near-full

No open-access source read states a cause for this pattern.

### Random

- **Randomly scattered failing dies are associated with ordinary process variation or a poorly controlled process environment rather than with one assignable source.** Confidence: medium.
  - "since they are merely artifacts of random process variation" (Ezzat et al., 2020; I. Introduction (randomly scattered defective chips))
  - "is often due to a lack of process environment management or factors that are difficult to control directly." (Kim et al., 2024; 3.2 Random Noise Filtering and Data Augmentation (about random noise, not the Random class))

### Scratch

- **Associated with wafer handling, moving or cutting.** Confidence: medium.
  - "Scratch is caused by machine handling, while Center and Edge-Ring are caused by thin film deposition and etching problems" (Zheng et al., 2021; 1. Introduction (citing refs. 4 and 5))
  - "The Scratch pattern indicates an exception in the moving or cutting processes." (Xu et al., 2022; 1. Introduction)

## Sources

- `ezzat2020`: Ahmed Aziz Ezzat, Sheng Liu, Dorit S. Hochbaum, Yu Ding. *A Graph-Theoretic Approach for Spatial Filtering and Its Impact on Mixed-type Spatial Pattern Recognition in Wafer Bin Maps*. arXiv preprint arXiv:2006.13824, 2020. Open access. https://arxiv.org/abs/2006.13824
- `zheng2021`: Huilin Zheng, Syed Waseem Abbas Sherazi, Sang Hyeok Son, Jong Yun Lee. *A Deep Convolutional Neural Network-Based Multi-Class Image Classification for Automatic Wafer Map Failure Recognition in Semiconductor Manufacturing*. Applied Sciences 11(20), 9769, 2021. Open access. https://doi.org/10.3390/app11209769
- `xu2022`: Qiao Xu, Naigong Yu, Firdaous Essaf. *Improved Wafer Map Inspection Using Attention Mechanism and Cosine Normalization*. Machines 10(2), 146, 2022. Open access. https://doi.org/10.3390/machines10020146
- `jeong2023`: Iljoo Jeong, Soo Young Lee, Keonhyeok Park, Iljeok Kim, Hyunsuk Huh, Seungchul Lee. *Wafer map failure pattern classification using geometric transformation-invariant convolutional neural network*. Scientific Reports 13, 8127, 2023. Open access. https://doi.org/10.1038/s41598-023-34147-2
- `kim2024`: Moo Hyun Kim, Tae Seon Kim. *Development of a Wafer Defect Pattern Classifier Using Polar Coordinate System Transformed Inputs and Convolutional Neural Networks*. Electronics 13(7), 1360, 2024. Open access. https://doi.org/10.3390/electronics13071360
