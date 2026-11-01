"use client";

import { useMemo, useRef, useState } from "react";

export interface ChartSeries {
  label: string;
  color: string;
  values: number[];
}

/**
 * Graphique en ligne SVG, sans dépendance externe (stack inchangée).
 * Supporte plusieurs séries partageant le même axe X (dates) avec un
 * curseur interactif au survol.
 */
export function LineChart({
  dates,
  series,
  height = 320,
  valueFormat = (v) => v.toLocaleString("fr-FR"),
}: {
  dates: string[];
  series: ChartSeries[];
  height?: number;
  valueFormat?: (v: number) => string;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const W = 800;
  const H = height;
  const padL = 8;
  const padR = 8;
  const padT = 12;
  const padB = 22;

  const { min, max } = useMemo(() => {
    let mn = Infinity;
    let mx = -Infinity;
    for (const s of series)
      for (const v of s.values) {
        if (!Number.isFinite(v)) continue;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
    if (!Number.isFinite(mn)) {
      mn = 0;
      mx = 1;
    }
    if (mn === mx) {
      mn -= 1;
      mx += 1;
    }
    return { min: mn, max: mx };
  }, [series]);

  const n = dates.length;
  const span = max - min || 1;
  const x = (i: number) =>
    padL + (i / Math.max(1, n - 1)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - (v - min) / span) * (H - padT - padB);

  function path(values: number[]) {
    return values
      .map((v, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`)
      .join(" ");
  }

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(
      ((px - padL) / (W - padL - padR)) * Math.max(1, n - 1)
    );
    setHover(Math.max(0, Math.min(n - 1, i)));
  }

  const ticks = useMemo(() => {
    const k = Math.min(6, n);
    return Array.from({ length: k }, (_, i) =>
      Math.round((i / Math.max(1, k - 1)) * (n - 1))
    );
  }, [n]);

  return (
    <div className="relative">
      <svg
        ref={ref}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        preserveAspectRatio="none"
      >
        {/* lignes de grille horizontales */}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <line
            key={t}
            x1={padL}
            x2={W - padR}
            y1={padT + t * (H - padT - padB)}
            y2={padT + t * (H - padT - padB)}
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={1}
          />
        ))}

        {series.map((s) => (
          <path
            key={s.label}
            d={path(s.values)}
            fill="none"
            stroke={s.color}
            strokeWidth={1.8}
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {/* curseur */}
        {hover != null && (
          <>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={padT}
              y2={H - padB}
              stroke="rgba(255,255,255,0.25)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
            {series.map((s) => (
              <circle
                key={s.label}
                cx={x(hover)}
                cy={y(s.values[hover])}
                r={3}
                fill={s.color}
              />
            ))}
          </>
        )}

        {/* labels X */}
        {ticks.map((i) => (
          <text
            key={i}
            x={x(i)}
            y={H - 6}
            fill="rgba(255,255,255,0.4)"
            fontSize={11}
            textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}
          >
            {dates[i]?.slice(2)}
          </text>
        ))}
      </svg>

      {/* tooltip */}
      {hover != null && (
        <div className="pointer-events-none absolute left-2 top-2 rounded-lg border border-white/10 bg-base-900/95 px-3 py-2 text-xs shadow-lg">
          <div className="mb-1 text-slate-400">{dates[hover]}</div>
          {series.map((s) => (
            <div key={s.label} className="flex items-center gap-2">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: s.color }}
              />
              <span className="text-slate-400">{s.label}</span>
              <span className="ml-auto font-medium text-slate-100">
                {valueFormat(s.values[hover])}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
