# lablab submission form texts (X5)

Event: AMD Developer Hackathon: ACT III. Track: **Intelligent Industry**.

Every number comes from [README.md](../../README.md), [STATUS.md](../STATUS.md) (Measured results) or the model cards ([SECOM](../model-cards/secom.md), [wafer maps](../model-cards/wafermap.md)). Each was measured on held-out data and is given with its 95% confidence interval. `check_form.py` checks the length limits.

## Title (max 60 characters)

<!-- title:start -->
Yield Guardian: checked AI investigations for chip yield
<!-- title:end -->

## Short description (max 255 characters)

<!-- short:start -->
A console for semiconductor yield engineers: control charts on a replayed production line, wafer-map pattern reading (macro-F1 0.900), and an AI investigator on AMD Token Factory whose report numbers are all checked before an engineer decides.
<!-- short:end -->

## Long description (about 300 to 500 words)

<!-- long:start -->
Yield Guardian is an investigation console for semiconductor yield engineers. When a production line drifts or wafers start failing, an engineer has to work out which sensors, which tools and which lots are involved, and then decide what to do. Yield Guardian collects the evidence, writes it up and checks it. The engineer makes the decision.

The console replays a real production line, SECOM: 1,567 units with 590 sensors from a semiconductor fab. Each unit is checked against multivariate control limits, Hotelling T² and SPE from a PCA reference period, plus EWMA and CUSUM charts on the leading sensor groups. On held-out in-control units, the T² chart flagged 1.9% (95% CI 0.2% to 6.6%) at its 99% limit. Sensor health rules flag dead, stuck, jumping and drifting sensors.

The wafer lab reads WM-811K wafer maps. A residual CNN classifies the defect pattern with macro-F1 0.900 (mean of 3 seeds, sd 0.006) on a split where no lot appears in both training and test. A hand-crafted feature baseline reaches 0.699. On the dataset's official split, where test lots differ from training lots, macro-F1 is 0.604; we report both. 96.0% of test wafers (95.7% to 96.3%) are classified automatically at precision 0.992, and the rest go to an engineer. A distance score on the model's embeddings marks maps unlike any known pattern, and similar past wafers are found with precision@10 of 0.860 (0.845 to 0.873).

When an alarm opens, an AI investigator calls read-only data tools, then writes a report from that evidence only. A verifier checks every number, citation and causal word in code, then with a model from a different family. A number that does not match its evidence is shown as unverified. The engineer approves or rejects, and the decision is logged. Language models never compute a statistic.

All language-model roles run on AMD GPUs through AMD Token Factory, one model per role:
- investigator: DeepSeek-V4.1-Flash
- report writer: MiMo-V2.6-Flash
- verifier: GLM-5.3-Flash
- engineer chat: Qwen3.8-Flash-Next
- router fallback: MiniCPM5-2B

The API key stays on the server.

We also report what did not work. On SECOM, the failure-risk model is not shown to be better than chance: on a test block of 313 units with 17 failures, LightGBM reached PR-AUC 0.075 (0.048 to 0.181) against a no-skill value of 0.054, and a logistic regression baseline reached 0.172. We did not tune until the test looked good. The product therefore leads with control charts, sensor health and wafer maps, and treats the SECOM risk score as an experimental signal. Findings about sensors are statistical associations, not causes.

Everything runs anywhere with Docker Compose. The model bundles are checked file by file against their SHA-256 manifests at build time and again at start-up. Without a Token Factory key, everything except the investigator and chat still works. Live at https://yield-guardian.anaslabs.com. The code is MIT-licensed, and the data licences and citations are in the README.
<!-- long:end -->

## Tags (5 to 8)

<!-- tags:start -->
- Semiconductor manufacturing
- Yield engineering
- Statistical process control
- Wafer map classification
- AI agents
- AMD Token Factory
- Intelligent Industry
<!-- tags:end -->
