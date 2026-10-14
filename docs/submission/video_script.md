# Demo video: script and shot list (X2)

About 3 minutes. Every number is taken from [README.md](../../README.md), [STATUS.md](../STATUS.md) (Measured results) or the model cards, and was measured on held-out data. The voice-over speaks at about 2.5 words per second.

Site: https://yield-guardian.anaslabs.com. Open it a minute before recording: the first request after idle wakes the app, which takes about 20 s.

**Before recording, check these screens.** On 2026-10-14 the screens at `/line` and `/investigations` exist. The wafer lab, lots, sensors, models and methods screens (STATUS U7 to U12) are in the navigation but not finished yet, so confirm their click paths when they land. The recorded investigations (L11) also need to be run once first, for the investigation scene.

## Shot list

| # | Seconds | Path | On screen and clicks | Voice-over |
|---|---|---|---|---|
| 1 | 15 | `/` | Home page. Slow scroll from the title to the measured-results panel. | "When a semiconductor line drifts, a yield engineer has to find which sensors, tools and lots are involved, and decide what to do, fast. Yield Guardian gathers and checks the evidence. The engineer decides." |
| 2 | 25 | `/line` | Click "Open the live line". The units table fills in real time. Hover the Hotelling T² chart, then the SPE chart, so the cursor shows the 99% and 99.9% limits. | "This is a replay of a real fab, SECOM: 1,567 units and 590 sensors. Every unit is checked against multivariate control limits, T² and SPE from a reference period, with EWMA and CUSUM on the leading sensor groups. On held-out in-control units the T² chart flagged 1.9% at its 99% limit, interval 0.2 to 6.6%." |
| 3 | 15 | `/line` | In "Open alarms", click the newest alarm. The alarm panel shows the unit, the statistic, its limit and the sensors contributing most. | "An alarm is written by code, not by a language model. It names the unit, the statistic, the limit it crossed, and the sensors that contribute most." |
| 4 | 35 | `/investigations/{id}` | Click "Investigate". The tool calls appear one by one. Scroll the report: each number has a check mark, and one value is marked unverified. Click "Approve", type a short note, confirm. Show the audit entry. | "The AI investigator calls read-only data tools and writes a report from that evidence only. A verifier then checks every number, citation and causal word in code, and again with a model from a different family. A value that does not match its evidence is shown as unverified. The engineer approves or rejects, and the decision is logged." |
| 5 | 30 | `/wafers` | Open a wafer whose pattern is shown as unknown. Show its predicted pattern and unknown-pattern score, then the row of most similar past wafers. Click one similar wafer. | "The wafer lab reads wafer maps from WM-811K. On lots never seen in training, the pattern classifier reaches macro-F1 0.900, against 0.699 for a hand-crafted baseline. 96% of wafers are classified automatically at precision 0.992; the rest go to an engineer. A map unlike any known pattern is marked unknown, and similar past wafers are found with precision at ten of 0.860." |
| 6 | 15 | `/lots` | Sort by flagged patterns. Open one flagged lot and show its stacked maps. | "Lots whose pattern counts are unusual are flagged with a binomial test and false-discovery control, and their wafers are stacked so the shared pattern is visible." |
| 7 | 25 | `/methods` | Scroll to the SECOM results table with intervals, then to the limitations list. | "We also show what did not work. On SECOM's test block of 313 units and 17 failures, the failure-risk model is not shown to be better than chance: PR-AUC 0.075, interval 0.048 to 0.181, against 0.054 for no skill. A logistic regression did better, at 0.172. We report it, and the product treats that risk score as experimental. Sensor findings are associations, not causes." |
| 8 | 15 | `/models` | Show the role table, then open the model selector for one role. | "Every language-model role runs on AMD GPUs through AMD Token Factory: DeepSeek-V4.1-Flash investigates, MiMo-V2.6-Flash writes, GLM-5.3-Flash verifies, Qwen3.8-Flash-Next answers chat, and MiniCPM5-2B routes. Language models never compute a statistic." |
| 9 | 10 | README "Run it anywhere", then `/` | Terminal: `docker compose -f deploy/compose/compose.yaml up -d --build --wait`. Cut to the home page with the site address. | "It runs anywhere with Docker Compose, with every model file checked against its checksum. Yield Guardian, for the Intelligent Industry track." |

The scenes add up to 185 seconds.

## Recording notes

- Keep the voice-over to the words above. Say each number as written, interval included where it is given.
- Do not show the Token Factory key, the admin session cookie or server logs.
- If an investigation run fails or gives a weak report, show it as it is, or record a different alarm. Do not edit the report text.
- End card: the project name, https://yield-guardian.anaslabs.com, the repository address, and "Track: Intelligent Industry, AMD Developer Hackathon: ACT III".
