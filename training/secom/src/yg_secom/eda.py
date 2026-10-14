"""Exploratory data analysis: counts, time structure, missingness, constants, duplicates.

The output feeds ``eda.json`` in the bundle and ``reports/eda.md``. All numbers are
computed from the loaded files; nothing is taken from documentation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from scipy import stats
from yg_common.estimates import Estimate
from yg_common.metrics import wilson_interval

from yg_secom import figures
from yg_secom.data import SecomData

NEAR_CONSTANT_SHARE = 0.95
MISSING_BINS = (
    ("0", 0.0, 0.0),
    ("(0, 1%]", 0.0, 0.01),
    ("(1%, 5%]", 0.01, 0.05),
    ("(5%, 20%]", 0.05, 0.20),
    ("(20%, 50%]", 0.20, 0.50),
    ("(50%, 100%)", 0.50, 1.0),
    ("100%", 1.0, 1.0),
)


def iso_utc(ts: pd.Timestamp) -> str:
    """ISO 8601 with a ``Z`` suffix (seconds precision)."""
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _quantiles(values: np.ndarray) -> dict[str, float]:
    q = np.quantile(values, [0.0, 0.25, 0.5, 0.75, 1.0])
    return {
        "min": float(q[0]),
        "q25": float(q[1]),
        "median": float(q[2]),
        "q75": float(q[3]),
        "max": float(q[4]),
        "mean": float(np.mean(values)),
    }


def week_start(timestamps: pd.Series) -> pd.Series:
    """Monday 00:00 of each timestamp's calendar week (ISO weeks)."""
    day = timestamps.dt.floor("D")
    return cast(pd.Series, day - pd.to_timedelta(day.dt.weekday, unit="D"))


def _missing_histogram(fraction: pd.Series) -> list[dict[str, Any]]:
    rows = []
    for label, low, high in MISSING_BINS:
        if label == "0":
            mask = fraction == 0.0
        elif label == "100%":
            mask = fraction == 1.0
        elif high == 1.0:
            mask = (fraction > low) & (fraction < 1.0)
        else:
            mask = (fraction > low) & (fraction <= high)
        rows.append({"bin": label, "features": int(mask.sum())})
    return rows


def _identical_column_groups(features: pd.DataFrame, columns: list[str]) -> list[list[str]]:
    """Groups of columns with identical values, missing positions included."""
    if not columns:
        return []
    block = features[columns]
    filled = block.fillna(np.inf)  # NaN never equals NaN; inf does not occur in the data
    keys = pd.util.hash_pandas_object(filled.T, index=False)
    groups: dict[int, list[str]] = {}
    for column, key in zip(columns, keys.to_numpy(), strict=True):
        groups.setdefault(int(key), []).append(column)
    confirmed: list[list[str]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        first = filled[members[0]].to_numpy()
        same = [m for m in members if np.array_equal(filled[m].to_numpy(), first)]
        if len(same) > 1:
            confirmed.append(same)
    return sorted(confirmed)


def compute_eda(data: SecomData) -> dict[str, Any]:
    """Every descriptive statistic of the raw data, as a JSON-ready dictionary."""
    X = data.features
    y = data.labels.astype(np.int64)
    ts = data.timestamps
    n, p = X.shape
    n_fail = int(y.sum())

    low, high = wilson_interval(n_fail, n)
    prevalence = Estimate(n_fail / n, low, high, 0.95, "Wilson score interval", n)

    day = ts.dt.floor("D")
    per_day = (
        pd.DataFrame({"day": day, "failed": y})
        .groupby("day", sort=True)
        .agg(units=("failed", "size"), failures=("failed", "sum"))
    )
    calendar_days = int((day.max() - day.min()).days) + 1
    weeks = week_start(ts)
    per_week = (
        pd.DataFrame({"week": weeks, "failed": y})
        .groupby("week", sort=True)
        .agg(units=("failed", "size"), failures=("failed", "sum"))
    )
    week_rows = []
    for week, row in per_week.iterrows():
        w_low, w_high = wilson_interval(int(row["failures"]), int(row["units"]))
        week_rows.append(
            {
                "week_start": iso_utc(pd.Timestamp(cast(Any, week))),
                "units": int(row["units"]),
                "failures": int(row["failures"]),
                "failure_rate": float(row["failures"] / row["units"]),
                "ci_low": w_low,
                "ci_high": w_high,
            }
        )
    table = np.column_stack(
        [per_week["failures"].to_numpy(), (per_week["units"] - per_week["failures"]).to_numpy()]
    )
    chi2 = stats.chi2_contingency(table)
    homogeneity = {
        "test": "chi-square test of homogeneity of the failure rate across calendar weeks",
        "statistic": float(chi2.statistic),
        "dof": int(chi2.dof),
        "p_value": float(chi2.pvalue),
        "weeks": int(per_week.shape[0]),
        "expected_failures_min": float(chi2.expected_freq[:, 0].min()),
        "caveat": "approximate when expected failure counts per week fall below 5",
    }

    missing = X.isna()
    per_feature = missing.mean(axis=0)
    per_unit = missing.mean(axis=1)
    nunique = X.nunique(dropna=True)
    all_missing = [c for c in X.columns if per_feature[c] == 1.0]
    constant = [c for c in X.columns if nunique[c] == 1]
    variable = [c for c in X.columns if nunique[c] > 1]
    near_constant = []
    for c in variable:
        counts = X[c].value_counts(dropna=True)
        share = float(counts.iloc[0] / counts.sum())
        if share >= NEAR_CONSTANT_SHARE:
            near_constant.append(
                {"sensor": c, "top_value": float(counts.index[0]), "top_value_share": share}
            )
    duplicate_columns = _identical_column_groups(X, variable)
    duplicate_rows = data.report["anomalies"]["units_in_duplicated_feature_rows"]

    top_missing = per_feature.sort_values(ascending=False, kind="mergesort").head(15)
    return {
        "counts": {
            "units": n,
            "features": p,
            "failures": n_fail,
            "passes": n - n_fail,
            "missing_cells": int(missing.to_numpy().sum()),
            "cells": int(n * p),
        },
        "class_balance": {
            "failure_prevalence": prevalence.to_dict(),
            "label_encoding": data.report["label_encoding"],
        },
        "time_range": {
            "first": iso_utc(ts.min()),
            "last": iso_utc(ts.max()),
            "span_days": float((ts.max() - ts.min()).total_seconds() / 86400.0),
            "calendar_days": calendar_days,
            "days_with_units": int(per_day.shape[0]),
            "days_without_units": int(calendar_days - per_day.shape[0]),
            "time_zone": data.report["time_zone"],
        },
        "units_per_day": {
            "summary": _quantiles(per_day["units"].to_numpy().astype(np.float64)),
            "days": [
                {
                    "date": cast(pd.Timestamp, d).strftime("%Y-%m-%d"),
                    "units": int(r["units"]),
                    "failures": int(r["failures"]),
                }
                for d, r in per_day.iterrows()
            ],
        },
        "failure_rate_by_week": week_rows,
        "failure_rate_homogeneity": homogeneity,
        "timestamps": {
            "parsing": data.report["timestamp_parsing"],
            **{
                k: v
                for k, v in data.report["anomalies"].items()
                if k.startswith(
                    ("timestamp", "units_sharing", "largest_tie", "file_order", "largest_back")
                )
            },
        },
        "missingness": {
            "overall_fraction": float(missing.to_numpy().mean()),
            "features_with_any_missing": int((per_feature > 0).sum()),
            "features_over_50_percent": int((per_feature > 0.5).sum()),
            "per_feature_fraction": _quantiles(per_feature.to_numpy()),
            "per_feature_histogram": _missing_histogram(per_feature),
            "per_unit_fraction": _quantiles(per_unit.to_numpy()),
            "units_with_no_readings": data.report["anomalies"]["units_with_no_readings"],
            "most_missing": [
                {"sensor": str(s), "missing_fraction": float(f)} for s, f in top_missing.items()
            ],
            "missing_fraction_by_sensor": {str(s): float(f) for s, f in per_feature.items()},
        },
        "constant_features": {
            "all_missing": all_missing,
            "single_value": constant,
            "count": len(all_missing) + len(constant),
            "definition": "no non-missing reading, or every non-missing reading identical",
        },
        "near_constant_features": {
            "definition": (
                f"not constant, and the most frequent non-missing value covers at least "
                f"{NEAR_CONSTANT_SHARE:.0%} of non-missing readings"
            ),
            "count": len(near_constant),
            "features": near_constant,
        },
        "duplicates": {
            "identical_feature_columns": duplicate_columns,
            "units_in_identical_feature_rows": duplicate_rows,
            "note": (
                "identical columns compare values and missing positions; constant columns excluded"
            ),
        },
    }


def write_eda_figures(data: SecomData, eda: dict[str, Any], directory: Path) -> dict[str, Path]:
    """Figures for the EDA report. Returns name -> PNG path."""
    out: dict[str, Path] = {}

    weeks = eda["failure_rate_by_week"]
    starts = pd.to_datetime([w["week_start"] for w in weeks])
    rate = np.array([w["failure_rate"] for w in weeks])
    lo = np.array([w["ci_low"] for w in weeks])
    hi = np.array([w["ci_high"] for w in weeks])
    fig, ax = figures.figure(6.4, 3.0)
    ax.fill_between(starts, lo * 100, hi * 100, color=figures.SERIES[0], alpha=0.12, linewidth=0)
    ax.plot(
        starts,
        rate * 100,
        color=figures.SERIES[0],
        marker="o",
        markersize=5,
        markeredgecolor=figures.SURFACE,
        markeredgewidth=1.5,
    )
    overall = eda["class_balance"]["failure_prevalence"]["value"] * 100
    ax.axhline(overall, color=figures.MUTED, linewidth=1.0)
    ax.annotate(
        f"overall {overall:.1f}%",
        (starts[-1], overall),
        xytext=(4, 4),
        textcoords="offset points",
        color=figures.INK_SECONDARY,
        fontsize=8,
    )
    ax.set_title("Failure rate by calendar week, with 95% Wilson intervals")
    ax.set_ylabel("failed units (%)")
    ax.set_ylim(bottom=0)
    fig.autofmt_xdate()
    out["failure_rate_by_week"] = figures.save(fig, directory / "eda_failure_rate_by_week.png")

    days = eda["units_per_day"]["days"]
    fig, ax = figures.figure(6.4, 2.8)
    ax.bar(
        pd.to_datetime([d["date"] for d in days]),
        [d["units"] for d in days],
        width=0.8,
        color=figures.SERIES[0],
    )
    ax.set_title("Units per production day")
    ax.set_ylabel("units")
    fig.autofmt_xdate()
    out["units_per_day"] = figures.save(fig, directory / "eda_units_per_day.png")

    hist = eda["missingness"]["per_feature_histogram"]
    fig, ax = figures.figure(6.4, 2.8)
    labels = [h["bin"] for h in hist]
    counts = [h["features"] for h in hist]
    ax.bar(labels, counts, width=0.6, color=figures.SERIES[0])
    for i, c in enumerate(counts):
        ax.annotate(
            str(c),
            (i, c),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            color=figures.INK_SECONDARY,
            fontsize=8,
        )
    ax.set_title("Sensors by share of missing readings")
    ax.set_xlabel("share of units with the reading missing")
    ax.set_ylabel("sensors")
    out["missingness"] = figures.save(fig, directory / "eda_missingness.png")
    return out


def _fmt_pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def eda_markdown(eda: dict[str, Any], figure_links: dict[str, str], provenance: str) -> str:
    """The EDA report in Markdown."""
    c = eda["counts"]
    prev = eda["class_balance"]["failure_prevalence"]
    tr = eda["time_range"]
    ts = eda["timestamps"]
    upd = eda["units_per_day"]["summary"]
    miss = eda["missingness"]
    const = eda["constant_features"]
    near = eda["near_constant_features"]
    dup = eda["duplicates"]
    hom = eda["failure_rate_homogeneity"]
    lines = [
        "# SECOM exploratory data analysis",
        "",
        provenance,
        "",
        "Every number on this page is computed from the source files by",
        "`yg_secom.eda`; nothing is copied from documentation.",
        "",
        "## Counts and class balance",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| Units (rows) | {c['units']:,} |",
        f"| Sensor features (columns) | {c['features']:,} |",
        f"| Failed final test | {c['failures']:,} |",
        f"| Passed final test | {c['passes']:,} |",
        f"| Failure prevalence | {_fmt_pct(prev['value'], 2)} "
        f"(95% Wilson CI {_fmt_pct(prev['ci_low'], 2)} to {_fmt_pct(prev['ci_high'], 2)}) |",
        f"| Missing cells | {c['missing_cells']:,} of {c['cells']:,} "
        f"({_fmt_pct(miss['overall_fraction'], 2)}) |",
        "",
        "## Time structure",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| First unit | {tr['first']} |",
        f"| Last unit | {tr['last']} |",
        f"| Span | {tr['span_days']:.1f} days ({tr['calendar_days']} calendar days) |",
        f"| Days with at least one unit | {tr['days_with_units']} |",
        f"| Calendar days without units | {tr['days_without_units']} |",
        f"| Units per production day (min / median / max) | {upd['min']:.0f} / "
        f"{upd['median']:.0f} / {upd['max']:.0f} |",
        f"| Timestamp format | `{ts['parsing']['format']}` "
        f"(example `{ts['parsing']['example']}`) |",
        f"| Timestamps whose day field exceeds 12 (proves day-first) | "
        f"{ts['parsing']['day_field_above_12']} |",
        f"| Timestamps also valid as month-first | {ts['parsing']['also_valid_month_first']} |",
        f"| File order is chronological | {'yes' if ts['file_order_is_chronological'] else 'no'} "
        f"({ts['file_order_backward_steps']} backward steps) |",
        f"| Units sharing a timestamp with another unit | {ts['units_sharing_a_timestamp']} "
        f"in {ts['timestamp_tie_groups']} groups (largest {ts['largest_tie_group']}) |",
        f"| Time zone | {tr['time_zone']} |",
        "",
        f"![Units per production day]({figure_links['units_per_day']})",
        "",
        "### Failure rate over time",
        "",
        f"![Failure rate by week]({figure_links['failure_rate_by_week']})",
        "",
        "| Week starting | Units | Failures | Failure rate | 95% Wilson CI |",
        "|---|---|---|---|---|",
    ]
    for w in eda["failure_rate_by_week"]:
        lines.append(
            f"| {w['week_start'][:10]} | {w['units']} | {w['failures']} | "
            f"{_fmt_pct(w['failure_rate'])} | {_fmt_pct(w['ci_low'])} to {_fmt_pct(w['ci_high'])} |"
        )
    lines += [
        "",
        f"A chi-square test of homogeneity across the {hom['weeks']} weeks gives "
        f"statistic {hom['statistic']:.2f} on {hom['dof']} degrees of freedom, "
        f"p = {hom['p_value']:.3g} (smallest expected weekly failure count "
        f"{hom['expected_failures_min']:.1f}; {hom['caveat']}).",
        "",
        "## Missingness",
        "",
        f"{miss['features_with_any_missing']} of {c['features']} sensors have at least one "
        f"missing reading; {miss['features_over_50_percent']} miss more than half.",
        f"Per unit, the share of missing readings ranges from "
        f"{_fmt_pct(miss['per_unit_fraction']['min'])} to "
        f"{_fmt_pct(miss['per_unit_fraction']['max'])} "
        f"(median {_fmt_pct(miss['per_unit_fraction']['median'])}).",
        f"Units with no readings at all: {len(miss['units_with_no_readings'])}.",
        "",
        f"![Missingness]({figure_links['missingness']})",
        "",
        "| Share of units missing | Sensors |",
        "|---|---|",
    ]
    lines += [f"| {h['bin']} | {h['features']} |" for h in miss["per_feature_histogram"]]
    lines += [
        "",
        "Most-missing sensors:",
        "",
        "| Sensor | Missing |",
        "|---|---|",
    ]
    lines += [
        f"| {m['sensor']} | {_fmt_pct(m['missing_fraction'])} |" for m in miss["most_missing"]
    ]
    lines += [
        "",
        "## Constant, near-constant and duplicated features",
        "",
        f"- Constant ({const['definition']}): {const['count']} sensors "
        f"({len(const['all_missing'])} never measured, "
        f"{len(const['single_value'])} single-valued).",
        f"- Near-constant ({near['definition']}): {near['count']} sensors.",
        f"- Groups of identical sensor columns ({dup['note']}): "
        f"{len(dup['identical_feature_columns'])}"
        + (
            " (" + "; ".join(", ".join(g) for g in dup["identical_feature_columns"][:10]) + ")"
            if dup["identical_feature_columns"]
            else ""
        )
        + ".",
        f"- Units whose {c['features']} readings duplicate another unit's: "
        f"{len(dup['units_in_identical_feature_rows'])}.",
        "",
        "The full lists are in `eda.json` (`constant_features`, `near_constant_features`,",
        "`duplicates`). No row is dropped because of any finding on this page.",
        "",
    ]
    return "\n".join(lines)
