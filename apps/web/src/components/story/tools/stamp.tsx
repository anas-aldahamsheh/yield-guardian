"use client";

import type { FinalTestResult } from "@yield-guardian/contracts";

import { formatInt } from "@/lib/format";
import { stageResult, type RunState } from "@/lib/live/run-state";

import { useScene, type SceneStore } from "../scene";

/**
 * Final test: the recorded results the input carries, stamped at the end of the line. The seal
 * counts units that passed and failed final test; the tally below has one mark per unit (pass or
 * fail colour, up to 70), outlined where the risk had warned. Wafers with a recorded label are counted by
 * whether the model's pattern matched it.
 */
export function StampTool({ state, store }: { state: RunState | null; store: SceneStore }) {
  const shown = useScene(store, (s) => s.revealed.has("final_test"));
  const stamp = useScene(store, (s) => s.stamp);
  const result: FinalTestResult | null = state && shown ? stageResult(state, "final_test") : null;
  const skipped = state?.stages.final_test.status === "skipped";
  const units = result?.units ?? [];
  const failed = result?.failed_units ?? 0;
  const passed = (result?.units_with_result ?? 0) - failed;
  const cols = 10;
  const cell = 10;
  const marks = units.slice(0, 70);
  const t = Math.min(1, stamp);

  return (
    <svg viewBox="0 0 200 250" className="block h-auto w-full" aria-hidden="true">
      {/* The seal: drawn once results arrive, inked by the stamp as it lands */}
      <g
        transform={`translate(100 92) rotate(-8) scale(${1.2 - 0.2 * t})`}
        opacity={result ? 0.25 + 0.75 * t : 1}
      >
        <circle
          r={60}
          fill="none"
          stroke={result ? "var(--ink-2)" : "var(--hairline)"}
          strokeWidth={1.5}
          strokeDasharray={result ? undefined : "3 4"}
        />
        <circle
          r={53}
          fill="none"
          stroke={result ? "var(--ink-2)" : "var(--hairline)"}
          strokeWidth={0.75}
        />
        <text y={-28} textAnchor="middle" fontSize={13} fill="var(--ink-2)">
          Final test
        </text>
        {result && result.units_with_result > 0 ? (
          <g className="tnum">
            <text
              y={9}
              textAnchor="middle"
              fontSize={34}
              fontWeight={300}
              fill={failed ? "var(--fail)" : "var(--pass)"}
            >
              {formatInt(failed)}
            </text>
            <text y={26} textAnchor="middle" fontSize={13} fill="var(--ink-2)">
              {failed === 1 ? "unit failed" : "units failed"}
            </text>
            <text y={41} textAnchor="middle" fontSize={12} fill="var(--ink-3)">
              {`${formatInt(passed)} passed`}
            </text>
          </g>
        ) : result && result.wafers_with_label > 0 ? (
          <g className="tnum">
            <text y={9} textAnchor="middle" fontSize={34} fontWeight={300} fill="var(--ink)">
              {formatInt(result.wafers_agreeing)}
            </text>
            <text y={26} textAnchor="middle" fontSize={13} fill="var(--ink-2)">
              {`of ${formatInt(result.wafers_with_label)} wafers`}
            </text>
            <text y={41} textAnchor="middle" fontSize={12} fill="var(--ink-3)">
              matched
            </text>
          </g>
        ) : (
          <text y={5} textAnchor="middle" fontSize={12} fill="var(--ink-3)">
            {skipped ? "no recorded results" : ""}
          </text>
        )}
      </g>
      {/* One mark per unit with a recorded result */}
      {marks.map((u, i) => {
        const x = 100 - (cols * cell) / 2 + (i % cols) * cell + 1;
        const y = 172 + Math.floor(i / cols) * cell;
        const visible = i < Math.round(t * marks.length);
        return (
          <g key={u.index} opacity={visible ? 1 : 0}>
            <rect
              x={x}
              y={y}
              width={cell - 2}
              height={cell - 2}
              rx={2}
              fill={u.result === "fail" ? "var(--fail)" : "var(--pass)"}
              opacity={u.result === "fail" ? 1 : 0.55}
            />
            {u.flagged ? (
              <rect
                x={x - 1}
                y={y - 1}
                width={cell}
                height={cell}
                rx={2.5}
                fill="none"
                stroke="var(--ink)"
                strokeWidth={1}
              />
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
