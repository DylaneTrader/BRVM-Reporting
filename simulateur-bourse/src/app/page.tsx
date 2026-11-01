"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { StatCard } from "@/components/StatCard";
import { CashPanel } from "@/components/CashPanel";
import { IndexStrip } from "@/components/IndexStrip";
import { formatFCFA, formatPct, pnlClass } from "@/lib/format";
import type { PortfolioSummary, Quote } from "@/types";

interface Sentiment {
  as_of: string;
  dominant_signal: string;
  ratio: number;
  n: number;
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [movers, setMovers] = useState<Quote[]>([]);
  const [sentiment, setSentiment] = useState<Sentiment | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    const [s, m, sig] = await Promise.all([
      fetch("/api/portfolio").then((r) => r.json()),
      fetch("/api/market").then((r) => r.json()),
      fetch("/api/signals").then((r) => r.json()),
    ]);
    setSummary(s);
    const quotes: Quote[] = (m.quotes || []).filter(
      (q: Quote) => q.changePct != null
    );
    quotes.sort((a, b) => (b.changePct ?? 0) - (a.changePct ?? 0));
    setMovers(quotes);
    if (sig?.meta?.concentration) {
      setSentiment({
        as_of: sig.meta.as_of,
        dominant_signal: sig.meta.concentration.dominant_signal,
        ratio: sig.meta.concentration.ratio,
        n: sig.meta.concentration.n,
      });
    }
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function reset() {
    if (!confirm("Réinitialiser le portefeuille (cash + positions + historique) ?"))
      return;
    const res = await fetch("/api/reset", { method: "POST" });
    const data = await res.json();
    setSummary(data.summary);
  }

  if (loading || !summary) {
    return <p className="py-20 text-center text-slate-400">Chargement…</p>;
  }

  const top = movers.slice(0, 5);
  const bottom = movers.slice(-5).reverse();

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tableau de bord</h1>
          <p className="text-sm text-slate-400">
            Valeur, performance et liquidités de votre portefeuille simulé.
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={reset}>
          Réinitialiser
        </button>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            Indices BRVM
          </h2>
          {sentiment && (
            <span className="text-xs text-slate-400">
              Sentiment IA :{" "}
              <span
                className={
                  sentiment.dominant_signal === "ACHAT"
                    ? "text-gain font-medium"
                    : sentiment.dominant_signal === "VENTE"
                    ? "text-loss font-medium"
                    : "text-slate-200 font-medium"
                }
              >
                {sentiment.dominant_signal}
              </span>{" "}
              ({Math.round(sentiment.ratio * 100)}% des {sentiment.n} valeurs)
            </span>
          )}
        </div>
        <IndexStrip />
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Valeur totale"
          value={formatFCFA(summary.totalValue)}
          sub={`dont ${formatFCFA(summary.holdingsValue)} en titres`}
          accent
        />
        <StatCard label="Liquidités" value={formatFCFA(summary.cash)} />
        <StatCard
          label="Plus/moins-value latente"
          value={formatFCFA(summary.totalUnrealizedPnl)}
          sub={formatPct(summary.totalUnrealizedPnlPct)}
          subClass={pnlClass(summary.totalUnrealizedPnl)}
        />
        <StatCard
          label="Performance globale"
          value={formatFCFA(summary.totalReturn)}
          sub={`${formatPct(summary.totalReturnPct)} · dépôts nets ${formatFCFA(
            summary.netDeposits
          )}`}
          subClass={pnlClass(summary.totalReturn)}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <CashPanel onChange={setSummary} />
        </div>

        <div className="lg:col-span-2 grid gap-6 sm:grid-cols-2">
          <MoversCard title="Plus fortes hausses" quotes={top} />
          <MoversCard title="Plus fortes baisses" quotes={bottom} />
        </div>
      </div>

      <div className="card">
        <h2 className="mb-3 text-lg font-semibold">Mes positions</h2>
        {summary.positions.length === 0 ? (
          <p className="text-sm text-slate-400">
            Aucune position. Rendez-vous sur le{" "}
            <a href="/market" className="text-brand-500 hover:underline">
              Marché
            </a>{" "}
            pour passer votre premier ordre.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {summary.positions.map((p) => (
              <div
                key={p.ticker}
                className="rounded-xl bg-base-900/70 px-3 py-2 text-sm"
              >
                <span className="font-medium">{p.code}</span>{" "}
                <span className="text-slate-400">×{p.quantity}</span>{" "}
                <span className={pnlClass(p.unrealizedPnl)}>
                  {formatPct(p.unrealizedPnlPct)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MoversCard({ title, quotes }: { title: string; quotes: Quote[] }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="card"
    >
      <h3 className="mb-3 text-sm font-semibold text-slate-300">{title}</h3>
      <div className="space-y-2">
        {quotes.map((q) => (
          <Link
            href={`/market/${q.symbol}`}
            key={q.symbol}
            className="flex items-center justify-between rounded-lg px-1 text-sm hover:bg-white/5"
          >
            <span className="truncate">
              <span className="font-medium">{q.code}</span>{" "}
              <span className="text-slate-500">{q.nom}</span>
            </span>
            <span className={pnlClass(q.changePct)}>{formatPct(q.changePct)}</span>
          </Link>
        ))}
      </div>
    </motion.div>
  );
}
