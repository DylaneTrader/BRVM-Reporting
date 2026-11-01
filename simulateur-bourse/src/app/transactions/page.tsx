"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { formatFCFA, formatNumber } from "@/lib/format";
import type { Transaction, TxType } from "@/types";

const TYPE_LABEL: Record<TxType, string> = {
  DEPOSIT: "Dépôt",
  WITHDRAW: "Retrait",
  BUY: "Achat",
  SELL: "Vente",
};

const TYPE_STYLE: Record<TxType, string> = {
  DEPOSIT: "bg-sky-600/20 text-sky-300",
  WITHDRAW: "bg-amber-600/20 text-amber-300",
  BUY: "bg-emerald-600/20 text-emerald-300",
  SELL: "bg-rose-600/20 text-rose-300",
};

export default function TransactionsPage() {
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/transactions?limit=500")
      .then((r) => r.json())
      .then((d) => {
        setTxs(d.transactions || []);
        setLoading(false);
      });
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Historique des transactions</h1>
        <p className="text-sm text-slate-400">
          Journal de toutes les opérations (dépôts, retraits, achats, ventes).
        </p>
      </div>

      {loading ? (
        <p className="py-20 text-center text-slate-400">Chargement…</p>
      ) : txs.length === 0 ? (
        <div className="card text-sm text-slate-400">Aucune transaction pour le moment.</div>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Valeur</th>
                <th className="px-4 py-3 text-right">Qté</th>
                <th className="px-4 py-3 text-right">Cours</th>
                <th className="px-4 py-3 text-right">Frais</th>
                <th className="px-4 py-3 text-right">Flux cash</th>
                <th className="px-4 py-3 text-right">Solde après</th>
              </tr>
            </thead>
            <tbody>
              {txs.map((t, i) => (
                <motion.tr
                  key={t.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: Math.min(i * 0.008, 0.25) }}
                  className="border-b border-white/5 hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-slate-400">
                    {new Date(t.createdAt).toLocaleString("fr-FR")}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                        TYPE_STYLE[t.type]
                      }`}
                    >
                      {TYPE_LABEL[t.type]}
                    </span>
                  </td>
                  <td className="px-4 py-3">{t.ticker ? t.ticker.split("_")[0] : "—"}</td>
                  <td className="px-4 py-3 text-right">
                    {t.quantity != null ? formatNumber(t.quantity) : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {t.price != null ? formatFCFA(t.price) : "—"}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-400">
                    {t.fees ? formatFCFA(t.fees) : "—"}
                  </td>
                  <td
                    className={`px-4 py-3 text-right ${
                      t.cashDelta >= 0 ? "text-gain" : "text-loss"
                    }`}
                  >
                    {t.cashDelta >= 0 ? "+" : ""}
                    {formatFCFA(t.cashDelta)}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300">
                    {formatFCFA(t.cashAfter)}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
