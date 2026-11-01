"use client";

import type { Fondamentaux } from "@/types";

/** Tableau des données fondamentales (CA, RN, BNPA, PER, dividende) par année. */
export function FondamentauxTable({ data }: { data: Fondamentaux | null }) {
  if (!data || !data.annees?.length) {
    return (
      <p className="text-sm text-slate-400">
        Données fondamentales non disponibles pour cette valeur.
      </p>
    );
  }

  const rows = Object.keys(data.metrics);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/5 text-xs uppercase tracking-wide text-slate-400">
            <th className="py-2 pr-4 text-left">Indicateur</th>
            {data.annees.map((y) => (
              <th key={y} className="px-3 py-2 text-right">
                {y}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((metric) => {
            const isGrowth = /croissance/i.test(metric);
            return (
              <tr key={metric} className="border-b border-white/5">
                <td className="py-2 pr-4 text-slate-300">{metric}</td>
                {data.annees.map((y) => {
                  const v = data.metrics[metric][y];
                  const neg = isGrowth && v?.startsWith("-");
                  const pos = isGrowth && v && !v.startsWith("-");
                  return (
                    <td
                      key={y}
                      className={`px-3 py-2 text-right tabular-nums ${
                        neg ? "text-loss" : pos ? "text-gain" : "text-slate-200"
                      }`}
                    >
                      {v ?? "—"}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
