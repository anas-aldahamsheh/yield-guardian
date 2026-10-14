# WM-811K: measured facts (W1, D5)

Measured by `uv run python -m wm.facts` from `data/interim/wm811k/wm811k.parquet`, which
`scripts/convert_lswmd.py` builds from the Kaggle mirror's `LSWMD.pkl` (SHA-256
`1d04fccb…5c65`; Parquet SHA-256 `31787547…f683`). Full numbers: `wm811k_facts.json`.

| Fact | Value |
|---|---|
| Rows (wafers) | 811,457 |
| Source columns | `waferMap`, `dieSize`, `lotName`, `waferIndex`, `trianTestLabel` (sic), `failureType` |
| Lots | 46,293 (PLAN §5 said 46,393; the data wins), names `lot1`…`lot47543`, each lot contiguous in the file |
| Wafers per lot | 1 to 25, median 24; `(lot, waferIndex)` is unique |
| `waferIndex` range | 1 to 25 |
| Labelled wafers | 172,950 (21.3%); unlabelled 638,507, stored as an empty array in `failureType` |
| Classes (labelled) | none 147,431; Edge-Ring 9,680; Edge-Loc 5,189; Center 4,294; Loc 3,593; Scratch 1,193; Random 866; Donut 555; Near-full 149 |
| Official split | Training 54,355; Test 118,595; absent 638,507. Every labelled wafer has a split and no unlabelled wafer has one |
| Lot overlap in the official split | **none**: 5,809 training lots, 4,953 test lots, 0 shared |
| Lots with labels | 10,762 (4,685 fully labelled, 6,077 partly labelled) |
| Lot numbers by official split | Training lot1–lot46729, Test lot40328–lot47542 |
| Values inside maps | {0, 1, 2} = no die, pass, fail |
| Map shapes | 632 distinct; heights 6–300, widths 3–205; most common 32×29 (108,687), 25×27 (64,083), 49×39 (39,323) |

## Consequences for training

- The official split is already lot-disjoint, so it does not leak lots. We still report the
  lot-grouped random split (PLAN §6.5 b) because the official test set has a very different class
  mix (74% `none` in training labels vs 93% in test) and covers mostly higher-numbered lots.
- Lot numbers are not documented as time, so "training-period rate" for the lot excursion test
  (W8) means the rate in the training split.
- `Near-full` has 149 labelled wafers in total (54 in official training), so its per-class metrics
  carry wide intervals.
