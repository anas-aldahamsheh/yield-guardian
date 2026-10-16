"use client";

import type { SensorHealth } from "@yield-guardian/contracts";
import { type KeyboardEvent, type MouseEvent, useEffect, useRef, useState } from "react";

import { formatPercent } from "@/lib/format";
import { HEALTH_STATUS, type HealthStatus } from "@/lib/labels";
import { cn } from "@/lib/utils";

/**
 * Every sensor as one tile, in column order (S001 at the top left, 30 to a row), coloured by its
 * health status. Dead sensors are drawn as an empty outline: there is nothing to read. Drawn on a
 * canvas because there are 590 tiles; the arrow keys move the selection and a live line reads it.
 */

export const FIELD_COLUMNS = 30;

const STATUS_TOKEN: Record<HealthStatus, string> = {
  ok: "--hairline-strong",
  watch: "--concern",
  maintenance: "--fail",
  dead: "--ink-3",
};

export function statusColour(status: HealthStatus): string {
  return `var(${STATUS_TOKEN[status]})`;
}

function token(el: Element, name: string): string {
  return getComputedStyle(el).getPropertyValue(name).trim() || "#888888";
}

export function SensorField({
  sensors,
  selected,
  onSelect,
  visible,
  className,
}: {
  sensors: SensorHealth[];
  selected: string | null;
  onSelect: (sensor: string) => void;
  /** Statuses drawn at full strength; the rest are faded. */
  visible: ReadonlySet<HealthStatus>;
  className?: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);
  const rows = Math.ceil(sensors.length / FIELD_COLUMNS);
  const selectedIndex = selected ? sensors.findIndex((s) => s.sensor === selected) : -1;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const draw = () => {
      const width = canvas.clientWidth;
      if (!width) return;
      const pitch = width / FIELD_COLUMNS;
      const height = pitch * rows;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.height = `${height}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const gap = pitch >= 12 ? 2 : 1;
      const colours = Object.fromEntries(
        Object.entries(STATUS_TOKEN).map(([k, v]) => [k, token(canvas, v)]),
      ) as Record<HealthStatus, string>;
      sensors.forEach((s, i) => {
        const status = s.status as HealthStatus;
        const x = (i % FIELD_COLUMNS) * pitch + gap / 2;
        const y = Math.floor(i / FIELD_COLUMNS) * pitch + gap / 2;
        const size = pitch - gap;
        ctx.globalAlpha = visible.has(status) ? 1 : 0.18;
        if (status === "dead") {
          ctx.strokeStyle = colours.dead;
          ctx.lineWidth = 1;
          ctx.strokeRect(x + 0.5, y + 0.5, size - 1, size - 1);
        } else {
          ctx.fillStyle = colours[status];
          ctx.fillRect(x, y, size, size);
        }
      });
      ctx.globalAlpha = 1;
      if (selectedIndex >= 0) {
        const x = (selectedIndex % FIELD_COLUMNS) * pitch;
        const y = Math.floor(selectedIndex / FIELD_COLUMNS) * pitch;
        ctx.strokeStyle = token(canvas, "--signal");
        ctx.lineWidth = 2;
        ctx.strokeRect(x - 1, y - 1, pitch + 2, pitch + 2);
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    const themeObserver = new MutationObserver(draw);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });
    return () => {
      observer.disconnect();
      themeObserver.disconnect();
    };
  }, [sensors, rows, selectedIndex, visible]);

  const indexAt = (e: MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const pitch = rect.width / FIELD_COLUMNS;
    const col = Math.floor((e.clientX - rect.left) / pitch);
    const row = Math.floor((e.clientY - rect.top) / pitch);
    const i = row * FIELD_COLUMNS + col;
    return col >= 0 && col < FIELD_COLUMNS && i >= 0 && i < sensors.length
      ? { i, x: e.clientX - rect.left, y: e.clientY - rect.top }
      : null;
  };

  const onKeyDown = (e: KeyboardEvent<HTMLCanvasElement>) => {
    const step: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -FIELD_COLUMNS,
      ArrowDown: FIELD_COLUMNS,
    };
    let next: number | null = null;
    if (e.key in step)
      next = Math.min(
        sensors.length - 1,
        Math.max(0, (selectedIndex < 0 ? 0 : selectedIndex) + step[e.key]!),
      );
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = sensors.length - 1;
    if (next == null) return;
    e.preventDefault();
    onSelect(sensors[next]!.sensor);
  };

  const hovered = hover ? sensors[hover.index] : undefined;
  const current = selectedIndex >= 0 ? sensors[selectedIndex] : undefined;

  return (
    <div className={cn("relative", className)}>
      <canvas
        ref={ref}
        tabIndex={0}
        role="img"
        aria-label={`Health of ${sensors.length} sensors, ${FIELD_COLUMNS} to a row. Arrow keys move between sensors.`}
        className="block w-full cursor-pointer rounded-[6px]"
        onPointerMove={(e) => {
          const at = indexAt(e);
          setHover(at ? { index: at.i, x: at.x, y: at.y } : null);
        }}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => {
          const at = indexAt(e);
          if (at) onSelect(sensors[at.i]!.sensor);
        }}
        onKeyDown={onKeyDown}
      />
      {hovered && hover ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-sm border border-hairline bg-surface px-2 py-1 text-[12px] leading-4 whitespace-nowrap text-ink shadow-sm"
          style={{ left: hover.x, top: hover.y + 16 }}
        >
          <span className="tnum font-medium">{hovered.sensor}</span>{" "}
          <span className="text-ink-2">{HEALTH_STATUS[hovered.status]}</span>
          <span className="tnum text-ink-3">, {formatPercent(hovered.missing_rate)} missing</span>
        </div>
      ) : null}
      <p className="sr-only" aria-live="polite">
        {current ? `${current.sensor}, ${HEALTH_STATUS[current.status]}.` : ""}
      </p>
    </div>
  );
}
