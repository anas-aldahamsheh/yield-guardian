"use client";

import { useQuery } from "@tanstack/react-query";
import { WAFER_CELL } from "@yield-guardian/contracts";
import {
  type KeyboardEvent,
  type PointerEvent,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import { ErrorState, Placeholder } from "@/components/states";
import { DieMap } from "@/components/wafer/die-map";
import { formatInt, plural } from "@/lib/format";
import { getDrawLayouts } from "@/lib/live/api";
import {
  DRAFT_KEYS,
  isDrawingDraft,
  readDraft,
  readJsonDraft,
  writeJsonDraft,
  type DrawingDraft,
} from "@/lib/live/drafts";
import { cn } from "@/lib/utils";

import {
  DRAWING_LOT,
  MAX_DRAWN_WAFERS,
  addWafer,
  brushCells,
  centreDie,
  clearWafer,
  dieCount,
  drawingDraft,
  drawnWafers,
  failCount,
  moveCursor,
  newDrawing,
  paint,
  removeWafer,
  restoreDrawing,
  selectWafer,
  strokeValue,
  type Brush,
  type Direction,
  type DrawLayout,
  type Drawing,
  type Paint,
} from "./draw-model";
import type { StartRun } from "./input-bar";

const KEYS: Record<string, Direction> = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
};

/**
 * Draw a defect: paint failing dies on a real WM-811K die layout (every die starts as pass), on
 * one to 25 wafers, and run them. With a pointer, a stroke paints fail, or pass when it starts on
 * a failing die. With the keyboard, the arrows move a cursor die by die, Space paints the die
 * under it, and Shift with an arrow paints while moving.
 */
export function DrawTool({ onStart, starting }: { onStart: StartRun; starting: boolean }) {
  const layouts = useQuery({
    queryKey: ["runs", "layouts"],
    queryFn: ({ signal }) => getDrawLayouts({ signal }),
    staleTime: 30 * 60_000,
  });
  // A drawing not run yet, kept for this tab so a reload keeps it (lib/live/drafts.ts).
  const [kept] = useState(() => readJsonDraft(DRAFT_KEYS.drawing, isDrawingDraft));
  const [layoutId, setLayoutId] = useState<string | null>(kept?.layoutId ?? null);
  const [changed, setChanged] = useState<Record<string, Drawing>>({});
  const items = useMemo(() => layouts.data?.items ?? [], [layouts.data]);
  const restored = useMemo(() => {
    const out: Record<string, Drawing> = {};
    for (const l of items) {
      const draft = kept?.edits[l.layout_id];
      const drawing = draft ? restoreDrawing(l, draft) : null;
      if (drawing) out[l.layout_id] = drawing;
    }
    return out;
  }, [kept, items]);
  const edits = useMemo(() => ({ ...restored, ...changed }), [restored, changed]);
  useKeptDrawing(layouts.data != null, layoutId, edits);
  const layout = items.find((l) => l.layout_id === layoutId) ?? items[0];
  const base = useMemo(() => (layout ? newDrawing(layout) : null), [layout]);

  if (layouts.isPending) return <Placeholder className="h-72" />;
  if (layouts.isError)
    return <ErrorState error={layouts.error} onRetry={() => void layouts.refetch()} compact />;
  if (!layout || !base)
    return <p className="text-[14px] text-ink-2">The API has no die layouts to draw on.</p>;

  const id = layout.layout_id;
  const drawing = edits[id] ?? base;
  const update = (fn: (d: Drawing) => Drawing) =>
    setChanged((e) => ({ ...e, [id]: fn(e[id] ?? restored[id] ?? base) }));

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-5">
      <LayoutChooser layouts={items} chosen={id} onChoose={setLayoutId} edited={edits} />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 md:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <Canvas drawing={drawing} onChange={update} />
        <Controls
          drawing={drawing}
          onChange={update}
          layout={layout}
          starting={starting}
          onRun={() => void onStart({ source: "drawn", wafers: drawnWafers(drawing) })}
        />
      </div>
    </div>
  );
}

/**
 * Keeps the drawing for this tab a moment after each change, and at once when the page is left
 * (a reload), so painting stays smooth. Only once the layouts are in: before that the drawing
 * kept from the last load is not back on them yet, and keeping it would lose it.
 */
function useKeptDrawing(
  ready: boolean,
  layoutId: string | null,
  drawings: Record<string, Drawing>,
) {
  const latest = useRef<{ layoutId: string | null; drawings: Record<string, Drawing> } | null>(
    null,
  );
  const save = useCallback(() => {
    const now = latest.current;
    if (!now) return;
    latest.current = null;
    // Only while the draw panel is the open way: closing it, or running the drawing, drops it.
    if (readDraft(DRAFT_KEYS.way) !== "draw") return;
    const ids = Object.keys(now.drawings);
    const draft: DrawingDraft | null =
      now.layoutId == null && !ids.length
        ? null
        : {
            layoutId: now.layoutId,
            edits: Object.fromEntries(ids.map((id) => [id, drawingDraft(now.drawings[id]!)])),
          };
    writeJsonDraft(DRAFT_KEYS.drawing, draft);
  }, []);
  useEffect(() => {
    if (!ready) return;
    latest.current = { layoutId, drawings };
    const timer = window.setTimeout(save, 400);
    return () => window.clearTimeout(timer);
  }, [ready, layoutId, drawings, save]);
  useEffect(() => {
    window.addEventListener("pagehide", save);
    return () => window.removeEventListener("pagehide", save);
  }, [save]);
}

function LayoutChooser({
  layouts,
  chosen,
  onChoose,
  edited,
}: {
  layouts: DrawLayout[];
  chosen: string;
  onChoose: (id: string) => void;
  edited: Record<string, Drawing>;
}) {
  return (
    <fieldset className="min-w-0">
      <legend className="text-[14px] leading-5 font-medium text-ink">Die layout</legend>
      <p className="text-[13px] leading-5 text-ink-3">
        The six most common map sizes in WM-811K, each the layout of a real wafer.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {layouts.map((l) => {
          const dies = dieCount(edited[l.layout_id] ?? newDrawing(l));
          const on = l.layout_id === chosen;
          return (
            <label
              key={l.layout_id}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-[4px] border border-hairline-strong px-2.5 py-1.5 text-[13px] leading-5 hover:bg-die-2 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
                on && "lit border-transparent",
              )}
            >
              <input
                type="radio"
                name="draw-layout"
                className="sr-only"
                checked={on}
                onChange={() => onChoose(l.layout_id)}
              />
              <span className="tnum text-ink">{`${l.map.height} by ${l.map.width}`}</span>
              <span className="tnum text-ink-3">{`${formatInt(dies)} dies`}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

/** Cells of the straight line between two dies, so a fast stroke leaves no gaps. */
function lineCells(width: number, from: number, to: number): [number, number][] {
  let x0 = from % width;
  let y0 = Math.floor(from / width);
  const x1 = to % width;
  const y1 = Math.floor(to / width);
  const dx = Math.abs(x1 - x0);
  const dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  const out: [number, number][] = [];
  for (;;) {
    out.push([y0, x0]);
    if (x0 === x1 && y0 === y1) return out;
    const e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x0 += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y0 += sy;
    }
  }
}

function Canvas({
  drawing,
  onChange,
}: {
  drawing: Drawing;
  onChange: (fn: (d: Drawing) => Drawing) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const help = useId();
  const [cursor, setCursor] = useState<number | null>(null);
  const [focused, setFocused] = useState(false);
  const [brush, setBrush] = useState<Brush>(1);
  const stroke = useRef<{ value: Paint; last: number } | null>(null);
  const [said, setSaid] = useState("");
  const map = drawing.wafers[drawing.current]!;
  const at = cursor ?? centreDie(drawing);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const draw = () => {
      const size = canvas.clientWidth;
      if (!size) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(size * dpr);
      canvas.height = Math.round(size * dpr);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);
      const css = getComputedStyle(canvas);
      const colour = (name: string, fallback: string) =>
        css.getPropertyValue(name).trim() || fallback;
      const n = Math.max(drawing.height, drawing.width);
      const pitch = size / n;
      const ox = (size - drawing.width * pitch) / 2;
      const oy = (size - drawing.height * pitch) / 2;
      const gap = pitch >= 6 ? 1 : 0.5;
      const pass = colour("--hairline-strong", "#4f4c43");
      const fail = colour("--fail", "#eb556e");
      for (let i = 0; i < map.length; i += 1) {
        const v = map[i];
        if (v === WAFER_CELL.noDie) continue;
        ctx.fillStyle = v === WAFER_CELL.fail ? fail : pass;
        ctx.fillRect(
          ox + (i % drawing.width) * pitch + gap / 2,
          oy + Math.floor(i / drawing.width) * pitch + gap / 2,
          pitch - gap,
          pitch - gap,
        );
      }
      if (focused && at >= 0) {
        const r = brush === 3 ? 1 : 0;
        ctx.strokeStyle = colour("--safelight", "#f5d326");
        ctx.lineWidth = 2;
        const x = ox + ((at % drawing.width) - r) * pitch;
        const y = oy + (Math.floor(at / drawing.width) - r) * pitch;
        ctx.strokeRect(x - 1, y - 1, pitch * (2 * r + 1) + 2, pitch * (2 * r + 1) + 2);
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [drawing, map, focused, at, brush]);

  const cellAt = (event: PointerEvent<HTMLCanvasElement>): number | null => {
    const box = event.currentTarget.getBoundingClientRect();
    const n = Math.max(drawing.height, drawing.width);
    const pitch = box.width / n;
    const col = Math.floor(
      (event.clientX - box.left - (box.width - drawing.width * pitch) / 2) / pitch,
    );
    const row = Math.floor(
      (event.clientY - box.top - (box.height - drawing.height * pitch) / 2) / pitch,
    );
    if (row < 0 || row >= drawing.height || col < 0 || col >= drawing.width) return null;
    return row * drawing.width + col;
  };

  const paintAlong = (from: number, to: number, value: Paint) => {
    const cells = lineCells(drawing.width, from, to).flatMap(([r, c]) =>
      brushCells(drawing, r, c, brush),
    );
    onChange((d) => paint(d, cells, value));
  };

  const describe = (d: Drawing, i: number) => {
    const row = Math.floor(i / d.width) + 1;
    const col = (i % d.width) + 1;
    const v = d.wafers[d.current]![i] === WAFER_CELL.fail ? "fail" : "pass";
    return `Row ${row}, column ${col}: ${v}.`;
  };

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const direction = KEYS[event.key];
    if (direction) {
      event.preventDefault();
      const next = moveCursor(drawing, at, direction);
      if (event.shiftKey) {
        const value = stroke.current?.value ?? strokeValue(drawing, at);
        stroke.current = { value, last: next };
        paintAlong(at, next, value);
      }
      setCursor(next);
      setSaid(describe(drawing, next));
      return;
    }
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      const value = strokeValue(drawing, at);
      const cells = brushCells(drawing, Math.floor(at / drawing.width), at % drawing.width, brush);
      const next = paint(drawing, cells, value);
      onChange(() => next);
      setSaid(
        `${describe(next, at)} ${plural(failCount(next.wafers[next.current]!), "die")} failing.`,
      );
    }
  };

  return (
    <div className="min-w-0">
      <div
        role="application"
        tabIndex={0}
        aria-label={`Wafer ${drawing.current + 1} of your drawing, ${drawing.height} by ${drawing.width} positions`}
        aria-describedby={help}
        onKeyDown={onKey}
        onKeyUp={(e) => {
          if (e.key === "Shift") stroke.current = null;
        }}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          stroke.current = null;
        }}
        className="relative aspect-square w-full max-w-[420px] rounded-full bg-die-2 outline-offset-4"
      >
        <canvas
          ref={ref}
          aria-hidden="true"
          className="block aspect-square w-full cursor-crosshair touch-none"
          onPointerDown={(e) => {
            const i = cellAt(e);
            if (i == null) return;
            e.currentTarget.setPointerCapture(e.pointerId);
            const value = strokeValue(drawing, i);
            stroke.current = { value, last: i };
            setCursor(i);
            paintAlong(i, i, value);
          }}
          onPointerMove={(e) => {
            const s = stroke.current;
            if (!s || !(e.buttons & 1)) return;
            const i = cellAt(e);
            if (i == null || i === s.last) return;
            paintAlong(s.last, i, s.value);
            stroke.current = { value: s.value, last: i };
            setCursor(i);
          }}
          onPointerUp={() => {
            stroke.current = null;
          }}
          onPointerCancel={() => {
            stroke.current = null;
          }}
        />
      </div>
      <p id={help} className="mt-2 max-w-[420px] text-[12px] leading-4 text-ink-3">
        Drag to paint failing dies; a stroke that starts on a failing die paints them back to pass.
        With the keyboard: arrows move, Space paints, Shift with an arrow paints while moving.
      </p>
      <p className="sr-only" aria-live="polite">
        {said}
      </p>
      <fieldset className="mt-3">
        <legend className="text-[13px] leading-5 text-ink-2">Brush</legend>
        <div className="mt-1 flex gap-2">
          {([1, 3] as const).map((b) => (
            <label
              key={b}
              className={cn(
                "cursor-pointer rounded-[4px] border border-hairline-strong px-2.5 py-1 text-[13px] leading-5 text-ink hover:bg-die-2 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
                brush === b && "lit border-transparent",
              )}
            >
              <input
                type="radio"
                name="draw-brush"
                className="sr-only"
                checked={brush === b}
                onChange={() => setBrush(b)}
              />
              {b === 1 ? "One die" : "3 by 3 dies"}
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}

function Controls({
  drawing,
  onChange,
  layout,
  starting,
  onRun,
}: {
  drawing: Drawing;
  onChange: (fn: (d: Drawing) => Drawing) => void;
  layout: DrawLayout;
  starting: boolean;
  onRun: () => void;
}) {
  const dies = dieCount(drawing);
  const failing = failCount(drawing.wafers[drawing.current]!);
  const n = drawing.wafers.length;
  const full = n >= MAX_DRAWN_WAFERS;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <p className="tnum text-[14px] leading-5 text-ink">
        {`Wafer ${drawing.current + 1}: ${formatInt(failing)} of ${formatInt(dies)} dies failing.`}
      </p>
      <div>
        <p className="text-[13px] leading-5 text-ink-2">{`Wafers in your drawing (${n} of up to ${MAX_DRAWN_WAFERS})`}</p>
        <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Wafers in your drawing">
          {drawing.wafers.map((map, k) => (
            <li key={k}>
              <button
                type="button"
                onClick={() => onChange((d) => selectWafer(d, k))}
                aria-pressed={k === drawing.current}
                aria-label={`Wafer ${k + 1}, ${plural(failCount(map), "die")} failing`}
                className={cn(
                  "block size-11 rounded-full p-0.5 hover:bg-die-2",
                  k === drawing.current && "lit",
                )}
              >
                <DieMap
                  data={{
                    kind: "results",
                    height: drawing.height,
                    width: drawing.width,
                    cells: map,
                  }}
                  label={`Wafer ${k + 1}`}
                  className="rounded-full"
                />
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex flex-wrap gap-2">
          <SmallButton disabled={full} onClick={() => onChange((d) => addWafer(d, true))}>
            Add a copy of this wafer
          </SmallButton>
          <SmallButton disabled={full} onClick={() => onChange((d) => addWafer(d, false))}>
            Add a blank wafer
          </SmallButton>
          <SmallButton disabled={!failing} onClick={() => onChange(clearWafer)}>
            Clear this wafer
          </SmallButton>
          <SmallButton disabled={n <= 1} onClick={() => onChange(removeWafer)}>
            Remove this wafer
          </SmallButton>
        </div>
      </div>
      <div className="mt-auto">
        <button
          type="button"
          onClick={onRun}
          disabled={starting}
          className="inline-flex h-10 items-center rounded-[4px] bg-ink px-4 text-[14px] font-semibold text-room hover:bg-ink/90 disabled:opacity-50"
        >
          {n === 1 ? "Run your drawing" : `Run your ${n} wafers`}
        </button>
        <p className="mt-2 max-w-[60ch] text-[12px] leading-4 text-ink-3">
          {`The run labels these maps as your drawing (lot "${DRAWING_LOT}"). A shape unlike the maps the model learned from still gets its nearest pattern, marked to check by eye. `}
          {layout.rule}
        </p>
      </div>
    </div>
  );
}

function SmallButton({
  children,
  disabled,
  onClick,
}: {
  children: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded-[4px] border border-hairline-strong px-2.5 py-1 text-[13px] leading-5 text-ink hover:bg-die-2 disabled:opacity-40"
    >
      {children}
    </button>
  );
}
