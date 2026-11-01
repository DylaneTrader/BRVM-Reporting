"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { TradeModal, type TradeContext } from "@/components/TradeModal";
import { SignalBadge } from "@/components/SignalBadge";
import { formatFCFA, formatPct, pnlClass } from "@/lib/format";
import type { Quote, PortfolioSummary, Signal } from "@/types";

export default function MarketPage() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [signals, setSignals] = useState<Record<string, Signal>>({});
  const [feeRate, setFeeRate] = useState(0.011);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [trade, setTrade] = useState<TradeContext | null>(null);

  async function load() {
    const [m, s, c, sig] = await Promise.all([
      fetch("/api/market").then((r) => r.json()),
      fetch("/api/portfolio").then((r) => r.json()),
      fetch("/api/config").then((r) => r.json()),
      fetch("/api/signals").then((r) => r.json()),
    ]);
    setQuotes(m.quotes || []);
    setSummary(s);
    setFeeRate(c.feeRate ?? 0.011);
    setSignals(sig.signals || {});
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return quotes;
    return quotes.filter(
      (x) =>
        x.nom.toLowerCase().includes(needle) ||
        x.code.toLowerCase().includes(needle) ||
        (x.secteur || "").toLowerCase().includes(needle)
    );
  }, [q, quotes]);

  function sharesOf(symbol: string): number {
    return summary?.positions.find((p) => p.ticker === symbol)?.quantity ?? 0;
  }

  function openTrade(quote: Quote, side: "buy" | "sell") {
    if (!summary) return;
    setTrade({
      quote,
      side,
      cash: summary.cash,
      sharesHeld: sharesOf(quote.symbol),
      feeRate,
    });
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Marché BRVM</h1>
          <p className="text-sm text-slate-400">
            {quotes.length} valeurs · cours de clôture
            {quotes[0]?.date ? ` au ${quotes[0].date}` : ""}.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {summary && (
            <span className="text-sm text-slate-400">
              Liquidités :{" "}
              <span className="font-medium text-slate-200">
                {formatFCFA(summary.cash)}
              </span>
            </span>
          )}
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Rechercher une valeur…"
            className="input sm:w-64"
          />
        </div>
      </div>

      {loading ? (
        <p className="py-20 text-center text-slate-400">Chargement…</p>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3">Valeur</th>
                <th className="px-4 py-3">Secteur</th>
                <th className="px-4 py-3 text-right">Cours</th>
                <th className="px-4 py-3 text-right">Var. jour</th>
                <th className="px-4 py-3 text-center">Signal IA</th>
                <th className="px-4 py-3 text-right">Détenu</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((x, i) => {
                const held = sharesOf(x.symbol);
                return (
                  <motion.tr
                    key={x.symbol}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: Math.min(i * 0.01, 0.3) }}
                    className="border-b border-white/5 hover:bg-white/5"
                  >
                    <td className="px-4 py-3">
                      <Link href={`/market/${x.symbol}`} className="group">
                        <div className="font-medium group-hover:text-brand-500">
                          {x.code}
                        </div>
                        <div className="text-xs text-slate-500">{x.nom}</div>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">
                      {x.secteur?.replace("BRVM - ", "") || "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-medium">
                      {formatFCFA(x.price)}
                    </td>
                    <td className={`px-4 py-3 text-right ${pnlClass(x.changePct)}`}>
                      {formatPct(x.changePct)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <SignalBadge signal={signals[x.symbol]?.signal} />
                    </td>
                    <td className="px-4 py-3 text-right text-slate-300">
                      {held > 0 ? held : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          className="btn-buy px-3 py-1.5"
                          onClick={() => openTrade(x, "buy")}
                        >
                          Acheter
                        </button>
                        <button
                          type="button"
                          className="btn-sell px-3 py-1.5"
                          disabled={held < 1}
                          onClick={() => openTrade(x, "sell")}
                        >
                          Vendre
                        </button>
                      </div>
                    </td>
                  </motion.tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <TradeModal
        ctx={trade}
        onClose={() => setTrade(null)}
        onDone={(s) => setSummary(s)}
      />
    </div>
  );
}
