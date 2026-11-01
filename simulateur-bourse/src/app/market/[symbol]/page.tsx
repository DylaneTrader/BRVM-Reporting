"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { LineChart } from "@/components/LineChart";
import { SignalBadge } from "@/components/SignalBadge";
import { FondamentauxTable } from "@/components/FondamentauxTable";
import { TradeModal, type TradeContext } from "@/components/TradeModal";
import { formatFCFA, formatPct, pnlClass } from "@/lib/format";
import type {
  Quote,
  PriceBar,
  Signal,
  Societe,
  Fondamentaux,
  Dividende,
  PortfolioSummary,
} from "@/types";

const PERIODS = [
  { label: "1M", n: 22 },
  { label: "3M", n: 66 },
  { label: "6M", n: 132 },
  { label: "1A", n: 264 },
  { label: "Max", n: 0 },
];

interface DetailResponse {
  quote: Quote;
  societe: Societe | null;
  signal: Signal | null;
  fondamentaux: Fondamentaux | null;
  dividende: Dividende | null;
  history: PriceBar[];
}

export default function StockDetailPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = use(params);
  const [data, setData] = useState<DetailResponse | null>(null);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [feeRate, setFeeRate] = useState(0.011);
  const [period, setPeriod] = useState(2); // 6M
  const [trade, setTrade] = useState<TradeContext | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    const n = PERIODS[period].n;
    fetch(`/api/market/${symbol}?history=${n}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setNotFound(true));
  }, [symbol, period]);

  useEffect(() => {
    Promise.all([
      fetch("/api/portfolio").then((r) => r.json()),
      fetch("/api/config").then((r) => r.json()),
    ]).then(([s, c]) => {
      setSummary(s);
      setFeeRate(c.feeRate ?? 0.011);
    });
  }, []);

  if (notFound)
    return (
      <p className="py-20 text-center text-slate-400">
        Valeur introuvable.{" "}
        <Link href="/market" className="text-brand-500 hover:underline">
          Retour au marché
        </Link>
      </p>
    );
  if (!data) return <p className="py-20 text-center text-slate-400">Chargement…</p>;

  const { quote, societe, signal, fondamentaux, dividende, history } = data;
  const held = summary?.positions.find((p) => p.ticker === symbol)?.quantity ?? 0;

  function openTrade(side: "buy" | "sell") {
    if (!summary) return;
    setTrade({ quote, side, cash: summary.cash, sharesHeld: held, feeRate });
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/market" className="text-sm text-slate-400 hover:text-slate-200">
          ← Marché
        </Link>
      </div>

      {/* En-tête */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{quote.code}</h1>
            <SignalBadge signal={signal?.signal} confidence={signal?.confidence} size="md" />
          </div>
          <p className="text-slate-400">{quote.nom}</p>
          <p className="mt-1 text-xs text-slate-500">
            {quote.secteur?.replace("BRVM - ", "")} · {symbol}
          </p>
        </div>
        <div className="flex items-end gap-4">
          <div className="text-right">
            <div className="text-2xl font-semibold">{formatFCFA(quote.price)}</div>
            <div className={pnlClass(quote.changePct)}>{formatPct(quote.changePct)}</div>
          </div>
          <div className="flex gap-2">
            <button className="btn-buy" onClick={() => openTrade("buy")}>
              Acheter
            </button>
            <button className="btn-sell" disabled={held < 1} onClick={() => openTrade("sell")}>
              Vendre
            </button>
          </div>
        </div>
      </div>

      {held > 0 && (
        <div className="rounded-xl bg-base-800/70 px-4 py-2 text-sm text-slate-300">
          Vous détenez <span className="font-semibold">{held}</span> titre(s) de cette valeur.
        </div>
      )}

      {/* Graphique */}
      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Cours de clôture</h2>
          <div className="flex gap-1">
            {PERIODS.map((p, i) => (
              <button
                key={p.label}
                onClick={() => setPeriod(i)}
                className={`rounded-lg px-2.5 py-1 text-xs ${
                  period === i
                    ? "bg-white/10 text-white"
                    : "text-slate-400 hover:bg-white/5"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        {history.length > 1 ? (
          <LineChart
            dates={history.map((b) => b.date)}
            series={[
              {
                label: "Clôture",
                color: "#10b981",
                values: history.map((b) => b.close),
              },
            ]}
            valueFormat={(v) => formatFCFA(v)}
          />
        ) : (
          <p className="text-sm text-slate-400">Historique insuffisant.</p>
        )}
      </div>

      {/* Signal Prophet + dividende */}
      <div className="grid gap-6 lg:grid-cols-2">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Signal IA Prophet (30 jours)
          </h3>
          {signal ? (
            <div className="space-y-2 text-sm">
              <Row label="Signal" value={<SignalBadge signal={signal.signal} confidence={signal.confidence} />} />
              <Row label="Cours actuel" value={formatFCFA(signal.last_price)} />
              <Row label="Cible 30j" value={formatFCFA(signal.target_30d)} />
              <Row
                label="Potentiel"
                value={
                  <span className={pnlClass(signal.target_30d - signal.last_price)}>
                    {formatPct(
                      signal.last_price
                        ? ((signal.target_30d - signal.last_price) / signal.last_price) * 100
                        : null
                    )}
                  </span>
                }
              />
              <Row label="Tendance" value={signal.trend === "UP" ? "Haussière ↑" : "Baissière ↓"} />
              <Row
                label="Fourchette 30j"
                value={`${formatFCFA(signal.yhat_lower)} – ${formatFCFA(signal.yhat_upper)}`}
              />
              <p className="pt-2 text-xs text-slate-500">
                Projection statistique (Prophet) — pas un conseil en investissement.
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Aucun signal disponible.</p>
          )}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Dividende à venir
          </h3>
          {dividende ? (
            <div className="space-y-2 text-sm">
              <Row label="Exercice" value={dividende.exercice} />
              <Row label="Montant net" value={formatFCFA(dividende.montantNet)} />
              <Row label="Rendement" value={formatPct(dividende.rendementPct)} />
              <Row label="Détachement" value={dividende.dateDetachement} />
              <Row label="Paiement" value={dividende.datePaiement} />
            </div>
          ) : (
            <p className="text-sm text-slate-400">Aucun dividende annoncé.</p>
          )}
        </motion.div>
      </div>

      {/* Fondamentaux */}
      <div className="card">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
          Données fondamentales
        </h3>
        <FondamentauxTable data={fondamentaux} />
      </div>

      {/* Société */}
      {societe && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
              À propos
            </h3>
            <p className="text-sm leading-relaxed text-slate-300">
              {societe.description || "Aucune description."}
            </p>
          </div>
          <div className="card">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
              Identité
            </h3>
            <div className="space-y-2 text-sm">
              <Row label="Secteur" value={societe.secteur?.replace("BRVM - ", "") || "—"} />
              <Row label="ISIN" value={societe.isin || "—"} />
              <Row label="PER" value={societe.per || "—"} />
              <Row label="Dividende" value={societe.dividende || "—"} />
              <Row label="Nombre de titres" value={societe.nombreTitres || "—"} />
            </div>
          </div>
        </div>
      )}

      <TradeModal ctx={trade} onClose={() => setTrade(null)} onDone={(s) => setSummary(s)} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-white/5 pb-2 last:border-0">
      <span className="text-slate-400">{label}</span>
      <span className="text-right font-medium text-slate-100">{value}</span>
    </div>
  );
}
