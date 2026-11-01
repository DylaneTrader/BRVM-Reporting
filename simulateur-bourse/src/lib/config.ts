import path from "path";

/**
 * Répertoire racine des données de marché BRVM.
 * Par défaut : dossier "data" d'un clone de Scraper-BRVM placé à côté de
 * BRVM-Reporting (même dossier parent).
 */
export const MARKET_DATA_DIR = path.resolve(
  process.cwd(),
  process.env.MARKET_DATA_DIR || "../../Scraper-BRVM/data"
);

export const ACTIONS_DIR = path.join(MARKET_DATA_DIR, "actions");
export const SOCIETES_DIR = path.join(MARKET_DATA_DIR, "societes");
export const INDICES_DIR = path.join(MARKET_DATA_DIR, "indices");
export const SIGNALS_DIR = path.join(MARKET_DATA_DIR, "signals");
export const ALGO_DIR = path.join(MARKET_DATA_DIR, "algo");
export const FOND_DIR = path.join(MARKET_DATA_DIR, "fondamentaux");
export const DIVIDENDES_DIR = path.join(MARKET_DATA_DIR, "dividendes");
export const RESUME_CSV = path.join(MARKET_DATA_DIR, "resume_scraping.csv");

/**
 * Taux de frais de courtage simulé (fraction du montant). Appliqué à l'achat
 * et à la vente. La BRVM applique en réalité plusieurs commissions cumulées
 * (courtage SGI + commission BRVM + DC/BR + taxe CREPMF), soit ~1 à 1,5 %.
 */
export const BROKERAGE_FEE_RATE = parseFloat(
  process.env.BROKERAGE_FEE_RATE || "0.011"
);

/** Dépôt initial offert à la création du compte (FCFA). */
export const INITIAL_CASH = parseFloat(process.env.INITIAL_CASH || "1000000");

/** Nom de l'utilisateur local par défaut (mono-utilisateur local). */
export const DEFAULT_USER_NAME = "local";
