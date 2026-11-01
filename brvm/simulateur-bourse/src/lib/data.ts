import fs from "fs";
import path from "path";
import {
  INDICES_DIR,
  SIGNALS_DIR,
  ALGO_DIR,
  FOND_DIR,
  DIVIDENDES_DIR,
  RESUME_CSV,
} from "./config";
import { parseFrNumber, getIndexHistory } from "./market";

/**
 * Données enrichies du dépôt Scraper-BRVM, reprises du dashboard HTML :
 *   - indices (data/indices)
 *   - signaux Prophet (data/signals/signals_latest.json + signals_history.json)
 *   - fondamentaux (data/fondamentaux)
 *   - allocation algorithmique Black-Litterman (data/algo/portfolio_latest.json)
 *   - dividendes à venir (data/dividendes/dividendes_a_venir.csv)
 */

// --- Cache JSON générique --------------------------------------------------

interface CacheEntry<T> {
  mtimeMs: number;
  value: T;
}
const jsonCache = new Map<string, CacheEntry<unknown>>();

function readJson<T>(filePath: string, fallback: T): T {
  let stat: fs.Stats;
  try {
    stat = fs.statSync(filePath);
  } catch {
    return fallback;
  }
  const cached = jsonCache.get(filePath);
  if (cached && cached.mtimeMs === stat.mtimeMs) return cached.value as T;
  try {
    const value = JSON.parse(fs.readFileSync(filePath, "utf8")) as T;
    jsonCache.set(filePath, { mtimeMs: stat.mtimeMs, value });
    return value;
  } catch {
    return fallback;
  }
}

// --- Indices ---------------------------------------------------------------

export interface IndexInfo {
  symbol: string;
  name: string;
  value: number;
  prevValue: number | null;
  changePct: number | null;
  date: string;
}

/** Symboles d'indices depuis le résumé (Type = Indice). */
export function listIndexSymbols(): string[] {
  try {
    const content = fs.readFileSync(RESUME_CSV, "utf8");
    return content
      .split(/\r?\n/)
      .slice(1)
      .map((l) => l.replace(/^﻿/, "").trim())
      .filter(Boolean)
      .map((l) => l.split(";"))
      .filter((c) => (c[1] || "").toLowerCase() === "indice")
      .map((c) => c[0].replace(/\./g, "_"));
  } catch {
    return [];
  }
}

export function getIndex(symbol: string): IndexInfo | null {
  const h = getIndexHistory(symbol);
  if (h.length === 0) return null;
  const info = readJson<{ Name?: string }>(
    path.join(INDICES_DIR, `${symbol}_info.json`),
    {}
  );
  const last = h[h.length - 1];
  const prev = h.length >= 2 ? h[h.length - 2] : null;
  const changePct =
    last.variationPct != null
      ? last.variationPct
      : prev && prev.close
      ? ((last.close - prev.close) / prev.close) * 100
      : null;
  return {
    symbol,
    name: info.Name || symbol.replace(/_/g, " "),
    value: last.close,
    prevValue: prev ? prev.close : null,
    changePct,
    date: last.date,
  };
}

/** Indices phares affichés en priorité, dans l'ordre. */
const HEADLINE_INDICES = ["BRVMC", "BRVM30", "BRVMPR", "BRVMPA"];

export function getHeadlineIndices(): IndexInfo[] {
  const available = new Set(listIndexSymbols());
  const ordered = [
    ...HEADLINE_INDICES.filter((s) => available.has(s)),
    ...[...available].filter((s) => !HEADLINE_INDICES.includes(s)),
  ];
  return ordered
    .map((s) => getIndex(s))
    .filter((x): x is IndexInfo => x !== null);
}

// --- Signaux Prophet -------------------------------------------------------

export interface Signal {
  ticker: string;
  last_price: number;
  last_date: string;
  signal: string; // "ACHAT" | "VENTE" | "NEUTRE"...
  confidence: string; // "Haute" | "Moyenne" | "Basse"
  target_30d: number;
  trend: string; // "UP" | "DOWN"
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
  train_annualized_return: number;
}

export interface SignalsPayload {
  generated_at: string;
  as_of: string;
  horizon_days: number;
  concentration_diagnostic: {
    concentrated: boolean;
    dominant_signal: string;
    ratio: number;
    n: number;
  } | null;
  signals: Record<string, Signal>;
}

export function getSignalsPayload(): SignalsPayload | null {
  return readJson<SignalsPayload | null>(
    path.join(SIGNALS_DIR, "signals_latest.json"),
    null
  );
}

export function getSignals(): Record<string, Signal> {
  return getSignalsPayload()?.signals ?? {};
}

export function getSignal(symbol: string): Signal | null {
  return getSignals()[symbol] ?? null;
}

/** Potentiel 30j en % (cible Prophet vs dernier cours). */
export function signalUpside(s: Signal): number | null {
  if (!s.last_price) return null;
  return ((s.target_30d - s.last_price) / s.last_price) * 100;
}

// --- Fondamentaux ----------------------------------------------------------

export interface Fondamentaux {
  ticker: string;
  annees: string[];
  metrics: Record<string, Record<string, string>>;
}

export function getFondamentaux(symbol: string): Fondamentaux | null {
  return readJson<Fondamentaux | null>(
    path.join(FOND_DIR, `${symbol}_fondamentaux.json`),
    null
  );
}

// --- Allocation algorithmique (Black-Litterman + Prophet) ------------------

export interface AlgoPortfolio {
  generated_at: string;
  allocation: Record<string, number>; // symbole -> poids (0..1)
  horizon_days: number;
  expected_return_30d: number;
  expected_volatility_30d: number;
  sharpe_ratio_30d: number;
}

export function getAlgoPortfolio(): AlgoPortfolio | null {
  return readJson<AlgoPortfolio | null>(
    path.join(ALGO_DIR, "portfolio_latest.json"),
    null
  );
}

// --- Dividendes à venir ----------------------------------------------------

export interface Dividende {
  ticker: string; // forme underscore "SIBC_ci"
  nom: string;
  exercice: string;
  dateDetachement: string;
  datePaiement: string;
  montantNet: number;
  rendementPct: number | null;
}

export function getDividendesAVenir(): Dividende[] {
  let content: string;
  try {
    content = fs.readFileSync(
      path.join(DIVIDENDES_DIR, "dividendes_a_venir.csv"),
      "utf8"
    );
  } catch {
    return [];
  }
  // Date_Scraping;Ticker;Nom_Canonique;Exercice;Statut;Date_Detachement;
  // Date_Paiement;Montant_Net_FCFA;Rendement_Pct;...
  const out: Dividende[] = [];
  const lines = content.split(/\r?\n/).slice(1);
  for (const raw of lines) {
    const line = raw.replace(/^﻿/, "").trim();
    if (!line) continue;
    const c = line.split(";");
    out.push({
      ticker: (c[1] || "").replace(/\./g, "_"),
      nom: c[2] || "",
      exercice: c[3] || "",
      dateDetachement: c[5] || "",
      datePaiement: c[6] || "",
      montantNet: parseFrNumber(c[7]) || 0,
      rendementPct: Number.isFinite(parseFrNumber(c[8]))
        ? parseFrNumber(c[8])
        : null,
    });
  }
  return out;
}
