"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Quote, PortfolioSummary } from "@/types";
import { formatFCFA, formatNumber } from "@/lib/format";

export interface TradeContext {
  quote: Quote;
  side: "buy" | "sell";
  cash: number;
  sharesHeld: number; // titres détenus (pour borne de vente)
  feeRate: number;
}

export function TradeModal({
  ctx,
  onClose,
  onDone,
}: {
  ctx: TradeContext | null;
  onClose: () => void;
  onDone: (summary: PortfolioSummary) => void;
}) {
  const [quantity, setQuantity] = useState<number>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setQuantity(1);
    setError(null);
  }, [ctx?.quote.symbol, ctx?.side]);

  const preview = useMemo(() => {
    if (!ctx) return null;
    const qty = Number.isFinite(quantity) ? Math.max(0, Math.floor(quantity)) : 0;
    const notional = qty * ctx.quote.price;
    const fees = Math.round(notional * ctx.feeRate);
    const total = ctx.side === "buy" ? notional + fees : notional - fees;
    return { qty, notional, fees, total };
  }, [ctx, quantity]);

  if (!ctx || !preview) return null;

  const isBuy = ctx.side === "buy";
  const maxAffordable = isBuy
    ? Math.floor(ctx.cash / (ctx.quote.price * (1 + ctx.feeRate)))
    : ctx.sharesHeld;

  const overBudget = isBuy && preview.total > ctx.cash;
  const overShares = !isBuy && preview.qty > ctx.sharesHeld;
  const invalidQty = preview.qty < 1;
  const blocked = overBudget || overShares || invalidQty || loading;

  async function submit() {
    if (!ctx || !preview) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: ctx.quote.symbol,
          side: ctx.side,
          quantity: preview.qty,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Erreur lors de l'ordre.");
        return;
      }
      onDone(data.summary as PortfolioSummary);
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-40 grid place-items-center bg-black/60 p-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          className="card w-full max-w-md"
          initial={{ scale: 0.95, y: 10, opacity: 0 }}
          animate={{ scale: 1, y: 0, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 26 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="mb-4 flex items-start justify-between">
            <div>
              <div className="text-xs text-slate-400">{ctx.quote.symbol}</div>
              <h2 className="text-lg font-semibold">{ctx.quote.nom}</h2>
            </div>
            <span
              className={`rounded-lg px-2 py-1 text-xs font-semibold ${
                isBuy ? "bg-emerald-600/20 text-emerald-400" : "bg-rose-600/20 text-rose-400"
              }`}
            >
              {isBuy ? "ACHAT" : "VENTE"}
            </span>
          </div>

          <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
            <Info label="Dernier cours" value={formatFCFA(ctx.quote.price)} />
            <Info
              label={isBuy ? "Liquidités dispo." : "Titres détenus"}
              value={isBuy ? formatFCFA(ctx.cash) : formatNumber(ctx.sharesHeld)}
            />
          </div>

          <label className="label">Quantité (titres)</label>
          <div className="mt-1 flex items-center gap-2">
            <input
              type="number"
              min={1}
              step={1}
              value={Number.isFinite(quantity) ? quantity : ""}
              onChange={(e) => setQuantity(parseInt(e.target.value, 10))}
              className="input"
            />
            <button
              type="button"
              className="btn-ghost whitespace-nowrap"
              onClick={() => setQuantity(Math.max(1, maxAffordable))}
            >
              Max ({formatNumber(Math.max(0, maxAffordable))})
            </button>
          </div>

          <div className="mt-4 space-y-1.5 rounded-xl bg-base-900/70 p-3 text-sm">
            <Row label="Montant" value={formatFCFA(preview.notional)} />
            <Row
              label="Frais de courtage"
              value={(isBuy ? "+ " : "− ") + formatFCFA(preview.fees)}
            />
            <div className="my-1 border-t border-white/5" />
            <Row
              label={isBuy ? "Total à débiter" : "Net à créditer"}
              value={formatFCFA(preview.total)}
              strong
            />
          </div>

          {error && (
            <p className="mt-3 rounded-lg bg-rose-600/15 px-3 py-2 text-sm text-rose-300">
              {error}
            </p>
          )}
          {!error && overBudget && (
            <p className="mt-3 text-sm text-rose-400">Liquidités insuffisantes.</p>
          )}
          {!error && overShares && (
            <p className="mt-3 text-sm text-rose-400">
              Vente à découvert interdite : quantité supérieure aux titres détenus.
            </p>
          )}

          <div className="mt-5 flex gap-2">
            <button className="btn-ghost flex-1" onClick={onClose}>
              Annuler
            </button>
            <button
              className={`flex-1 ${isBuy ? "btn-buy" : "btn-sell"}`}
              disabled={blocked}
              onClick={submit}
            >
              {loading ? "Exécution…" : isBuy ? "Acheter" : "Vendre"}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-base-900/70 p-3">
      <div className="label">{label}</div>
      <div className="mt-0.5 font-medium">{value}</div>
    </div>
  );
}

function Row({
  label,
  value,
  strong,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-400">{label}</span>
      <span className={strong ? "font-semibold text-white" : "text-slate-200"}>
        {value}
      </span>
    </div>
  );
}
