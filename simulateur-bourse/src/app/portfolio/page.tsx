"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TradeModal, type TradeContext } from "@/components/TradeModal";
import { StatCard } from "@/components/StatCard";
import { formatFCFA, formatNumber, formatPct, pnlClass } from "@/lib/format";
import type { PortfolioSummary, Quote } from "@/types";

export default function PortfolioPage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [feeRate, setFeeRate] = useState(0.011);
  const [loading, setLoading] = useState(true);
  const [trade, setTrade] = useState<TradeContext | null>(null);

  async function load() {
    const [s, c] = await Promise.all([
      fetch("/api/portfolio").then((r) => r.json()),
      fetch("/api/config").then((r) => r.json()),
    ]);
    setSummary(s);
    setFeeRate(c.feeRate ?? 0.011);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  if (loading || !summary) {
    return <p className="py-20 text-center text-slate-400">Chargement…</p>;
  }

  function openSell(p: PortfolioSummary["positions"][number]) {
    if (!summary || p.lastPrice == null) return;
    const quote: Quote = {
      symbol: p.ticker,
      code: p.code,
      nom: p.nom,
      secteur: null,
      price: p.lastPrice,
      prevClose: null,
      changePct: null,
      date: "",
    };
    setTrade({ quote, side: "sell", cash: summary.cash, sharesHeld: p.quantity, feeRate });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Mon portefeuille</h1>
        <p className="text-sm text-slate-400">
          Positions valorisées au dernier cours de clôture.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Valeur totale" value={formatFCFA(summary.totalValue)} accent />
        <StatCard label="Titres" value={formatFCFA(summary.holdingsValue)} />
        <StatCard label="Liquidités" value={formatFCFA(summary.cash)} />
        <StatCard
          label="+/- value latente"
          value={formatFCFA(summary.totalUnrealizedPnl)}
          sub={formatPct(summary.totalUnrealizedPnlPct)}
          subClass={pnlClass(summary.totalUnrealizedPnl)}
        />
      </div>

      <div className="card overflow-x-auto p-0">
        {summary.positions.length === 0 ? (
          <p className="p-6 text-sm text-slate-400">
            Aucune position. Passez un ordre depuis le{" "}
            <a href="/market" className="text-brand-500 hover:underline">
              Marché
            </a>
            .
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3">Valeur</th>
                <th className="px-4 py-3 text-right">Qté</th>
                <th className="px-4 py-3 text-right">PRU</th>
                <th className="px-4 py-3 text-right">Cours</th>
                <th className="px-4 py-3 text-right">Investi</th>
                <th className="px-4 py-3 text-right">Valorisation</th>
                <th className="px-4 py-3 text-right">+/- value</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {summary.positions.map((p) => (
                <motion.tr
                  key={p.ticker}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="border-b border-white/5 hover:bg-white/5"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium">{p.code}</div>
                    <div className="text-xs text-slate-500">{p.nom}</div>
                  </td>
                  <td className="px-4 py-3 text-right">{formatNumber(p.quantity)}</td>
                  <td className="px-4 py-3 text-right">{formatFCFA(p.avgCost)}</td>
                  <td className="px-4 py-3 text-right">
                    {p.lastPrice != null ? formatFCFA(p.lastPrice) : "—"}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300">
                    {formatFCFA(p.invested)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {p.marketValue != null ? formatFCFA(p.marketValue) : "—"}
                  </td>
                  <td className={`px-4 py-3 text-right ${pnlClass(p.unrealizedPnl)}`}>
                    {p.unrealizedPnl != null ? formatFCFA(p.unrealizedPnl) : "—"}
                    <div className="text-xs">{formatPct(p.unrealizedPnlPct)}</div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button className="btn-sell px-3 py-1.5" onClick={() => openSell(p)}>
                      Vendre
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <TradeModal ctx={trade} onClose={() => setTrade(null)} onDone={(s) => setSummary(s)} />
    </div>
  );
}
