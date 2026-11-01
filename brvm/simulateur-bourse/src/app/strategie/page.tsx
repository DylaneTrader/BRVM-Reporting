"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { StatCard } from "@/components/StatCard";
import { SignalBadge } from "@/components/SignalBadge";
import { formatFCFA, formatNumber, formatPct, pnlClass } from "@/lib/format";
import type { Strategie } from "@/types";

export default function StrategiePage() {
  const [data, setData] = useState<Strategie | null>(null);
  const [capital, setCapital] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load(cap?: string) {
    setLoading(true);
    const url = cap ? `/api/strategie?capital=${encodeURIComponent(cap)}` : "/api/strategie";
    const res = await fetch(url);
    const json = await res.json();
    if (!res.ok) {
      setError(json.error || "Indisponible.");
      setLoading(false);
      return;
    }
    setData(json);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  if (loading && !data)
    return <p className="py-20 text-center text-slate-400">Chargement…</p>;
  if (error)
    return (
      <div className="card text-sm text-slate-400">
        {error} L'allocation algorithmique provient de{" "}
        <code className="text-slate-300">data/algo/portfolio_latest.json</code>.
      </div>
    );
  if (!data) return null;

  const totalDiv = data.dividendes.reduce((s, d) => s + d.montantNet, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Stratégie suggérée
        </h1>
        <p className="text-sm text-slate-400">
          Allocation cible Black-Litterman × signaux Prophet (horizon{" "}
          {data.horizonDays} j). Générée le{" "}
          {new Date(data.generatedAt).toLocaleString("fr-FR")}.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Rendement attendu 30j"
          value={formatPct(data.metrics.expectedReturn30d * 100)}
          subClass={pnlClass(data.metrics.expectedReturn30d)}
          accent
        />
        <StatCard
          label="Volatilité 30j"
          value={formatPct(data.metrics.expectedVolatility30d * 100)}
        />
        <StatCard
          label="Ratio de Sharpe 30j"
          value={data.metrics.sharpe30d.toFixed(2)}
        />
        <StatCard
          label="Dividendes attendus"
          value={formatFCFA(totalDiv)}
          sub={`${data.dividendes.length} ligne(s)`}
        />
      </div>

      {/* Capital simulé */}
      <div className="card flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="label">Capital à allouer</div>
          <p className="text-sm text-slate-400">
            Par défaut, la valeur totale de votre portefeuille.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={0}
            step={10000}
            value={capital}
            placeholder={String(Math.round(data.capital))}
            onChange={(e) => setCapital(e.target.value)}
            className="input sm:w-48"
          />
          <button className="btn-primary" onClick={() => load(capital)}>
            Recalculer
          </button>
        </div>
      </div>

      {/* Plan d'action */}
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="px-4 py-3">Valeur</th>
              <th className="px-4 py-3 text-right">Poids cible</th>
              <th className="px-4 py-3 text-right">Cours</th>
              <th className="px-4 py-3 text-right">Titres cibles</th>
              <th className="px-4 py-3 text-right">Détenus</th>
              <th className="px-4 py-3 text-center">Signal</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {data.lines.map((l) => (
              <motion.tr
                key={l.ticker}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="border-b border-white/5 hover:bg-white/5"
              >
                <td className="px-4 py-3">
                  <Link href={`/market/${l.ticker}`} className="hover:underline">
                    <span className="font-medium">{l.code}</span>
                    <span className="ml-2 text-xs text-slate-500">{l.nom}</span>
                  </Link>
                </td>
                <td className="px-4 py-3 text-right">{(l.weight * 100).toFixed(2)} %</td>
                <td className="px-4 py-3 text-right">
                  {l.price != null ? formatFCFA(l.price) : "—"}
                </td>
                <td className="px-4 py-3 text-right">{formatNumber(l.targetShares)}</td>
                <td className="px-4 py-3 text-right text-slate-400">
                  {l.currentShares > 0 ? formatNumber(l.currentShares) : "—"}
                </td>
                <td className="px-4 py-3 text-center">
                  <SignalBadge signal={l.signal} />
                </td>
                <td className="px-4 py-3 text-right">
                  {l.action === "HOLD" ? (
                    <span className="text-slate-500">Conserver</span>
                  ) : (
                    <span
                      className={
                        l.action === "BUY" ? "text-gain font-medium" : "text-loss font-medium"
                      }
                    >
                      {l.action === "BUY" ? "Acheter" : "Vendre"} {Math.abs(l.deltaShares)}
                    </span>
                  )}
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-500">
        Le plan d'action compare l'allocation cible (pour le capital indiqué) à vos
        positions actuelles. Exécutez les ordres manuellement depuis chaque fiche
        valeur. Outil éducatif — aucune recommandation d'investissement.
      </p>
    </div>
  );
}
