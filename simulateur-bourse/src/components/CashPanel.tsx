"use client";

import { useState } from "react";
import type { PortfolioSummary } from "@/types";

export function CashPanel({
  onChange,
}: {
  onChange: (summary: PortfolioSummary) => void;
}) {
  const [amount, setAmount] = useState<string>("");
  const [loading, setLoading] = useState<"deposit" | "withdraw" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(action: "deposit" | "withdraw") {
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Saisissez un montant positif.");
      return;
    }
    setLoading(action);
    setError(null);
    try {
      const res = await fetch("/api/cash", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, amount: value }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Erreur.");
        return;
      }
      onChange(data.summary as PortfolioSummary);
      setAmount("");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="card">
      <h2 className="mb-1 text-lg font-semibold">Liquidités</h2>
      <p className="mb-4 text-sm text-slate-400">
        Déposez ou retirez de l'argent fictif.
      </p>
      <label className="label">Montant (FCFA)</label>
      <input
        type="number"
        min={0}
        step={1000}
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        placeholder="100 000"
        className="input mt-1"
      />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          className="btn-primary"
          disabled={loading !== null}
          onClick={() => submit("deposit")}
        >
          {loading === "deposit" ? "…" : "Déposer"}
        </button>
        <button
          className="btn-ghost"
          disabled={loading !== null}
          onClick={() => submit("withdraw")}
        >
          {loading === "withdraw" ? "…" : "Retirer"}
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
    </div>
  );
}
