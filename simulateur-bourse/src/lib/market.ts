import fs from "fs";
import path from "path";
import { ACTIONS_DIR, SOCIETES_DIR, INDICES_DIR, RESUME_CSV } from "./config";

/**
 * Couche d'accès aux données de marché BRVM.
 *
 * Source réelle (mise à jour quotidiennement par GitHub Actions dans le dépôt
 * parent) :
 *   - data/actions/{SYMBOL}_historique.csv  -> OHLCV journalier (séparateur ";",
 *     décimales à la virgule, ex. "3 300,0").
 *   - data/resume_scraping.csv              -> dernier cours + métadonnées.
 *   - data/societes/{SYMBOL}_societe.json   -> fiche société (nom, secteur...).
 *
 * Le SYMBOL canonique utilisé en interne est de la forme "SGBC_ci"
 * (le résumé note "SGBC.ci" -> on remplace "." par "_").
 */

export interface PriceBar {
  date: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number; // nombre de titres
  valueFCFA: number; // volume en FCFA
  variationPct: number | null;
}

export interface Societe {
  symbol: string;
  nom: string;
  secteur: string | null;
  isin: string | null;
  per: string | null;
  dividende: string | null;
  description: string | null;
  nombreTitres: string | null;
}

export interface Quote {
  symbol: string; // "SGBC_ci"
  code: string; // "SGBC"
  nom: string;
  secteur: string | null;
  price: number; // dernier cours de clôture (FCFA)
  prevClose: number | null; // clôture précédente
  changePct: number | null; // variation jour (%)
  date: string; // date du dernier cours
}

// --- Parsing utilitaires --------------------------------------------------

/** "3 300,0" / "21 483,0" / "-7,36" -> nombre. Chaîne vide -> NaN. */
export function parseFrNumber(raw: string | undefined | null): number {
  if (raw == null) return NaN;
  const cleaned = raw
    .replace(/ /g, "") // espace insécable
    .replace(/\s/g, "") // espaces de milliers
    .replace(/%/g, "")
    .replace(",", ".")
    .trim();
  if (cleaned === "") return NaN;
  return Number(cleaned);
}

/** "SGBC.ci" -> "SGBC_ci" */
function toSymbol(resumeTicker: string): string {
  return resumeTicker.replace(/\./g, "_");
}

// --- Cache en mémoire (invalidé par mtime du fichier) ---------------------

interface CacheEntry<T> {
  mtimeMs: number;
  value: T;
}

const historyCache = new Map<string, CacheEntry<PriceBar[]>>();
const societeCache = new Map<string, CacheEntry<Societe | null>>();

function readFileWithCache<T>(
  filePath: string,
  cache: Map<string, CacheEntry<T>>,
  parser: (content: string) => T,
  fallback: T
): T {
  let stat: fs.Stats;
  try {
    stat = fs.statSync(filePath);
  } catch {
    return fallback;
  }
  const cached = cache.get(filePath);
  if (cached && cached.mtimeMs === stat.mtimeMs) return cached.value;
  const content = fs.readFileSync(filePath, "utf8");
  const value = parser(content);
  cache.set(filePath, { mtimeMs: stat.mtimeMs, value });
  return value;
}

// --- Historique de prix ---------------------------------------------------

function parseHistory(content: string): PriceBar[] {
  const lines = content.split(/\r?\n/);
  const bars: PriceBar[] = [];
  // Saute l'en-tête (avec éventuel BOM).
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].replace(/^﻿/, "").trim();
    if (!line) continue;
    const c = line.split(";");
    // Date;Ouverture;Plus_Haut;Plus_Bas;Cloture;Volume_Titres;Volume_FCFA;Variation_Pct
    const close = parseFrNumber(c[4]);
    if (!Number.isFinite(close)) continue;
    bars.push({
      date: c[0],
      open: parseFrNumber(c[1]),
      high: parseFrNumber(c[2]),
      low: parseFrNumber(c[3]),
      close,
      volume: parseFrNumber(c[5]) || 0,
      valueFCFA: parseFrNumber(c[6]) || 0,
      variationPct: Number.isFinite(parseFrNumber(c[7])) ? parseFrNumber(c[7]) : null,
    });
  }
  // Les fichiers sont déjà triés par date croissante, mais on s'en assure.
  bars.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  return bars;
}

export function getHistory(symbol: string): PriceBar[] {
  const file = path.join(ACTIONS_DIR, `${symbol}_historique.csv`);
  return readFileWithCache(file, historyCache, parseHistory, []);
}

/** Historique d'un indice (même format OHLCV que les actions). */
export function getIndexHistory(symbol: string): PriceBar[] {
  const file = path.join(INDICES_DIR, `${symbol}_historique.csv`);
  return readFileWithCache(file, historyCache, parseHistory, []);
}

// --- Fiche société --------------------------------------------------------

function parseSociete(symbol: string, content: string): Societe | null {
  try {
    const j = JSON.parse(content);
    return {
      symbol,
      nom: j["Nom"] || symbol,
      secteur: j["Secteur"] || null,
      isin: j["ISIN"] || null,
      per: j["PER"] || null,
      dividende: j["Dividende"] || null,
      description: j["La société"] || null,
      nombreTitres: j["Nombre_Titres"] || j["Nombre de titres"] || null,
    };
  } catch {
    return null;
  }
}

export function getSociete(symbol: string): Societe | null {
  const file = path.join(SOCIETES_DIR, `${symbol}_societe.json`);
  return readFileWithCache(
    file,
    societeCache,
    (content) => parseSociete(symbol, content),
    null
  );
}

// --- Liste des valeurs (résumé) -------------------------------------------

let resumeCache: CacheEntry<string[]> | null = null;

/** Liste des symboles d'actions (type "Action") depuis le résumé de scraping. */
export function listStockSymbols(): string[] {
  let stat: fs.Stats;
  try {
    stat = fs.statSync(RESUME_CSV);
  } catch {
    // Repli : déduire depuis les fichiers du dossier actions.
    try {
      return fs
        .readdirSync(ACTIONS_DIR)
        .filter((f) => f.endsWith("_historique.csv"))
        .map((f) => f.replace("_historique.csv", ""))
        .sort();
    } catch {
      return [];
    }
  }
  if (resumeCache && resumeCache.mtimeMs === stat.mtimeMs) return resumeCache.value;

  const content = fs.readFileSync(RESUME_CSV, "utf8");
  const lines = content.split(/\r?\n/);
  const symbols: string[] = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].replace(/^﻿/, "").trim();
    if (!line) continue;
    const c = line.split(";");
    // Ticker;Type;Nb_Lignes;Date_Min;Date_Max;Dernier_Cours
    if ((c[1] || "").toLowerCase() === "action") {
      symbols.push(toSymbol(c[0]));
    }
  }
  symbols.sort();
  resumeCache = { mtimeMs: stat.mtimeMs, value: symbols };
  return symbols;
}

// --- Cotations ------------------------------------------------------------

/** Dernier cours coté pour un symbole (clôture la plus récente), ou null. */
export function getLatestPrice(symbol: string): number | null {
  const h = getHistory(symbol);
  if (h.length === 0) return null;
  return h[h.length - 1].close;
}

/** Cotation enrichie (cours, variation jour, nom, secteur). */
export function getQuote(symbol: string): Quote | null {
  const h = getHistory(symbol);
  if (h.length === 0) return null;
  const last = h[h.length - 1];
  const prev = h.length >= 2 ? h[h.length - 2] : null;
  const soc = getSociete(symbol);
  const changePct =
    last.variationPct != null
      ? last.variationPct
      : prev && prev.close
      ? ((last.close - prev.close) / prev.close) * 100
      : null;
  return {
    symbol,
    code: symbol.split("_")[0],
    nom: soc?.nom || symbol,
    secteur: soc?.secteur || null,
    price: last.close,
    prevClose: prev ? prev.close : null,
    changePct,
    date: last.date,
  };
}

/** Toutes les cotations (pour la page Marché). */
export function getAllQuotes(): Quote[] {
  return listStockSymbols()
    .map((s) => getQuote(s))
    .filter((q): q is Quote => q !== null)
    .sort((a, b) => a.nom.localeCompare(b.nom));
}

/** Map symbole -> dernier cours, pour valoriser un portefeuille en un appel. */
export function getPriceMap(symbols: string[]): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const s of symbols) out[s] = getLatestPrice(s);
  return out;
}

/** Vrai si le symbole est une valeur connue et cotée. */
export function isTradable(symbol: string): boolean {
  return getLatestPrice(symbol) !== null;
}
