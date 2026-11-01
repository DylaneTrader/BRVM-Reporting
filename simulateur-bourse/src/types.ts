// Types partagés client/serveur (formes JSON renvoyées par l'API).

export interface Quote {
  symbol: string;
  code: string;
  nom: string;
  secteur: string | null;
  price: number;
  prevClose: number | null;
  changePct: number | null;
  date: string;
}

export interface PriceBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  valueFCFA: number;
  variationPct: number | null;
}

export interface PositionView {
  ticker: string;
  code: string;
  nom: string;
  quantity: number;
  avgCost: number;
  lastPrice: number | null;
  invested: number;
  marketValue: number | null;
  unrealizedPnl: number | null;
  unrealizedPnlPct: number | null;
}

export interface PortfolioSummary {
  cash: number;
  positions: PositionView[];
  holdingsValue: number;
  totalValue: number;
  totalInvested: number;
  totalUnrealizedPnl: number;
  totalUnrealizedPnlPct: number | null;
  netDeposits: number;
  totalReturn: number;
  totalReturnPct: number | null;
}

export type TxType = "DEPOSIT" | "WITHDRAW" | "BUY" | "SELL";

export interface Transaction {
  id: string;
  type: TxType;
  ticker: string | null;
  quantity: number | null;
  price: number | null;
  fees: number;
  cashDelta: number;
  cashAfter: number;
  createdAt: string;
}

export interface TradePreview {
  notional: number;
  fees: number;
  total: number;
}

export interface IndexInfo {
  symbol: string;
  name: string;
  value: number;
  prevValue: number | null;
  changePct: number | null;
  date: string;
}

export interface Signal {
  ticker: string;
  last_price: number;
  last_date: string;
  signal: string;
  confidence: string;
  target_30d: number;
  trend: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
  train_annualized_return: number;
  upside?: number | null;
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

export interface Fondamentaux {
  ticker: string;
  annees: string[];
  metrics: Record<string, Record<string, string>>;
}

export interface Dividende {
  ticker: string;
  nom: string;
  exercice: string;
  dateDetachement: string;
  datePaiement: string;
  montantNet: number;
  rendementPct: number | null;
}

export interface StrategieLine {
  ticker: string;
  code: string;
  nom: string;
  weight: number;
  price: number | null;
  targetValue: number;
  targetShares: number;
  currentShares: number;
  deltaShares: number;
  action: "BUY" | "SELL" | "HOLD";
  signal: string | null;
  upside: number | null;
}

export interface Strategie {
  generatedAt: string;
  horizonDays: number;
  metrics: {
    expectedReturn30d: number;
    expectedVolatility30d: number;
    sharpe30d: number;
  };
  capital: number;
  lines: StrategieLine[];
  dividendes: Dividende[];
}
