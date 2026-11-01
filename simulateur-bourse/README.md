# Simulateur de portefeuille boursier — BRVM

Application **locale** de simulation de portefeuille boursier sur la **BRVM**
(Bourse Régionale des Valeurs Mobilières). Déposez des liquidités fictives,
achetez/vendez des actions au dernier cours connu, et suivez la valeur de votre
portefeuille ainsi que l'historique des transactions.

## Stack

- **Frontend** : Next.js 15 (App Router), TypeScript, Tailwind CSS, Framer Motion
- **Backend** : Next.js API Routes (runtime Node.js), logique métier, lecture des données de marché
- **Base de données** : SQLite locale + Prisma ORM (tables `User`, `Portfolio`, `Holding`, `Transaction`)

## Source des données de marché

Les cotations proviennent du dépôt de données **DylaneTrader/Scraper-BRVM**, cloné à côté de
BRVM-Reporting et mis à jour
quotidiennement par GitHub Actions :

| Donnée | Fichier |
| --- | --- |
| Historique OHLCV par valeur | `data/actions/{SYMBOL}_historique.csv` |
| Dernier cours + métadonnées | `data/resume_scraping.csv` |
| Fiche société (nom, secteur, ISIN…) | `data/societes/{SYMBOL}_societe.json` |

> Remarque : le fichier `Composition_flottante.xlsx` contient les **pondérations
> flottantes**, pas les prix. La source de prix réellement utilisée est donc le
> CSV `actions/`. Le package `xlsx` reste installé si vous souhaitez exploiter le
> classeur de pondérations.

Le chemin est configurable via `MARKET_DATA_DIR` dans `.env`
(par défaut `../../Scraper-BRVM/data`, c'est-à-dire un clone de Scraper-BRVM placé à côté de
BRVM-Reporting).

## Réalisme de la simulation

- **Pas de vente à découvert** (règle BRVM) : impossible de vendre plus de titres
  que l'on détient.
- **Titres entiers** uniquement.
- **Frais de courtage** simulés sur achat **et** vente (`BROKERAGE_FEE_RATE`,
  défaut ~1,1 %), agrégeant les commissions BRVM réelles (courtage SGI,
  commission BRVM, DC/BR, taxe CREPMF).
- **Exécution au dernier cours de clôture** disponible.
- **PRU** (prix de revient unitaire) moyen pondéré, frais d'achat inclus, pour le
  calcul des plus/moins-values.

## Démarrage

```bash
cd simulateur-bourse
npm install
npm run setup     # crée la base SQLite + portefeuille initial
npm run dev       # http://localhost:3000
```

## Configuration (`.env`)

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `DATABASE_URL` | Base SQLite | `file:./dev.db` |
| `MARKET_DATA_DIR` | Dossier des données de marché | `../../Scraper-BRVM/data` |
| `BROKERAGE_FEE_RATE` | Taux de frais (fraction) | `0.011` |
| `INITIAL_CASH` | Cash initial à la création | `1000000` |

## API

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/market` | Toutes les cotations |
| GET | `/api/market/[symbol]` | Cotation + fiche + historique |
| GET | `/api/portfolio` | Synthèse du portefeuille |
| POST | `/api/cash` | Dépôt / retrait |
| GET/POST | `/api/trade` | Aperçu / exécution d'un ordre |
| GET | `/api/transactions` | Historique |
| POST | `/api/reset` | Réinitialisation |
| GET | `/api/config` | Paramètres publics (frais…) |
| GET | `/api/indices` | Indices BRVM (BRVMC, BRVM30…) |
| GET | `/api/signals` | Signaux Prophet + sentiment de marché |
| GET | `/api/strategie` | Allocation Black-Litterman + plan d'action |

## Données enrichies (reprises du dashboard HTML)

Intégrées depuis `brvm_dashboard_enriched.html`, en restant sur la même stack
(aucune dépendance de graphe externe — composant `LineChart` SVG maison) :

- **Indices BRVM** sur le tableau de bord (`data/indices`).
- **Signaux IA Prophet** (ACHAT/VENTE/NEUTRE + cible 30 j) en badge sur le marché
  et le dashboard (`data/signals/signals_latest.json`).
- **Fiche valeur** `/market/[symbol]` : graphique de cours (1M→Max), signal Prophet,
  dividende à venir, données fondamentales (`data/fondamentaux`), fiche société.
- **Stratégie** `/strategie` : allocation cible Black-Litterman
  (`data/algo/portfolio_latest.json`), rendement/volatilité/Sharpe 30 j, dividendes
  attendus (`data/dividendes`) et **plan d'action** (titres cibles vs détenus).

> Non portés (outils analytiques moins centraux pour un simulateur) : le
> simulateur de rebalancement J+2 et le backtest Base-100 complet. Faciles à
> ajouter ultérieurement à partir des mêmes fichiers.
