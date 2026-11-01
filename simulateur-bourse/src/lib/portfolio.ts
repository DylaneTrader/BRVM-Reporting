import { prisma } from "./prisma";
import { DEFAULT_USER_NAME, INITIAL_CASH } from "./config";
import { buyCost, sellProceeds } from "./fees";
import { getLatestPrice, getQuote, isTradable } from "./market";
import type { Portfolio } from "@prisma/client";

/**
 * Logique métier du simulateur. Toutes les opérations qui modifient l'argent ou
 * les positions s'exécutent dans une transaction SQL (atomicité).
 *
 * Règles de réalisme BRVM :
 *  - Quantités en titres entiers (>= 1).
 *  - Pas de vente à découvert : on ne peut vendre que ce qu'on détient.
 *  - Le cash ne peut jamais devenir négatif (frais inclus).
 *  - Exécution au dernier cours de clôture connu.
 *  - PRU (prix de revient unitaire) moyen pondéré, frais d'achat inclus.
 */

export class TradeError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
    this.name = "TradeError";
  }
}

export async function getOrCreatePortfolio(): Promise<Portfolio> {
  const existing = await prisma.portfolio.findFirst({
    where: { user: { name: DEFAULT_USER_NAME } },
  });
  if (existing) return existing;

  const user = await prisma.user.upsert({
    where: { name: DEFAULT_USER_NAME },
    update: {},
    create: { name: DEFAULT_USER_NAME },
  });

  return prisma.portfolio.create({
    data: {
      userId: user.id,
      cash: INITIAL_CASH,
      // Dépôt initial tracé comme transaction si non nul.
      transactions:
        INITIAL_CASH > 0
          ? {
              create: {
                type: "DEPOSIT",
                fees: 0,
                cashDelta: INITIAL_CASH,
                cashAfter: INITIAL_CASH,
              },
            }
          : undefined,
    },
  });
}

// --- Valorisation ---------------------------------------------------------

export interface PositionView {
  ticker: string;
  code: string;
  nom: string;
  quantity: number;
  avgCost: number; // PRU
  lastPrice: number | null;
  invested: number; // quantity * avgCost
  marketValue: number | null; // quantity * lastPrice
  unrealizedPnl: number | null;
  unrealizedPnlPct: number | null;
}

export interface PortfolioSummary {
  cash: number;
  positions: PositionView[];
  holdingsValue: number; // somme des valeurs de marché
  totalValue: number; // cash + holdingsValue
  totalInvested: number; // somme des montants investis (PRU)
  totalUnrealizedPnl: number;
  totalUnrealizedPnlPct: number | null;
  netDeposits: number; // dépôts - retraits
  totalReturn: number; // totalValue - netDeposits
  totalReturnPct: number | null;
}

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  const portfolio = await getOrCreatePortfolio();
  const holdings = await prisma.holding.findMany({
    where: { portfolioId: portfolio.id, quantity: { gt: 0 } },
    orderBy: { ticker: "asc" },
  });

  const positions: PositionView[] = holdings.map((h) => {
    const quote = getQuote(h.ticker);
    const lastPrice = quote?.price ?? null;
    const invested = h.quantity * h.avgCost;
    const marketValue = lastPrice != null ? h.quantity * lastPrice : null;
    const unrealizedPnl = marketValue != null ? marketValue - invested : null;
    const unrealizedPnlPct =
      unrealizedPnl != null && invested > 0
        ? (unrealizedPnl / invested) * 100
        : null;
    return {
      ticker: h.ticker,
      code: h.ticker.split("_")[0],
      nom: quote?.nom || h.ticker,
      quantity: h.quantity,
      avgCost: h.avgCost,
      lastPrice,
      invested,
      marketValue,
      unrealizedPnl,
      unrealizedPnlPct,
    };
  });

  const holdingsValue = positions.reduce(
    (s, p) => s + (p.marketValue ?? p.invested),
    0
  );
  const totalInvested = positions.reduce((s, p) => s + p.invested, 0);
  const totalUnrealizedPnl = positions.reduce(
    (s, p) => s + (p.unrealizedPnl ?? 0),
    0
  );
  const totalValue = portfolio.cash + holdingsValue;

  // Dépôts nets = somme des cashDelta des DEPOSIT/WITHDRAW.
  const cashFlows = await prisma.transaction.aggregate({
    where: { portfolioId: portfolio.id, type: { in: ["DEPOSIT", "WITHDRAW"] } },
    _sum: { cashDelta: true },
  });
  const netDeposits = cashFlows._sum.cashDelta ?? 0;
  const totalReturn = totalValue - netDeposits;

  return {
    cash: portfolio.cash,
    positions,
    holdingsValue,
    totalValue,
    totalInvested,
    totalUnrealizedPnl,
    totalUnrealizedPnlPct:
      totalInvested > 0 ? (totalUnrealizedPnl / totalInvested) * 100 : null,
    netDeposits,
    totalReturn,
    totalReturnPct: netDeposits > 0 ? (totalReturn / netDeposits) * 100 : null,
  };
}

// --- Liquidités -----------------------------------------------------------

export async function deposit(amount: number) {
  if (!Number.isFinite(amount) || amount <= 0)
    throw new TradeError("INVALID_AMOUNT", "Le montant doit être positif.");
  const portfolio = await getOrCreatePortfolio();
  const cashAfter = portfolio.cash + amount;
  return prisma.$transaction(async (tx) => {
    await tx.portfolio.update({
      where: { id: portfolio.id },
      data: { cash: cashAfter },
    });
    return tx.transaction.create({
      data: {
        portfolioId: portfolio.id,
        type: "DEPOSIT",
        fees: 0,
        cashDelta: amount,
        cashAfter,
      },
    });
  });
}

export async function withdraw(amount: number) {
  if (!Number.isFinite(amount) || amount <= 0)
    throw new TradeError("INVALID_AMOUNT", "Le montant doit être positif.");
  const portfolio = await getOrCreatePortfolio();
  if (amount > portfolio.cash)
    throw new TradeError(
      "INSUFFICIENT_CASH",
      "Solde de liquidités insuffisant pour ce retrait."
    );
  const cashAfter = portfolio.cash - amount;
  return prisma.$transaction(async (tx) => {
    await tx.portfolio.update({
      where: { id: portfolio.id },
      data: { cash: cashAfter },
    });
    return tx.transaction.create({
      data: {
        portfolioId: portfolio.id,
        type: "WITHDRAW",
        fees: 0,
        cashDelta: -amount,
        cashAfter,
      },
    });
  });
}

// --- Achat / Vente --------------------------------------------------------

function validateQuantity(quantity: number) {
  if (!Number.isInteger(quantity) || quantity < 1)
    throw new TradeError(
      "INVALID_QUANTITY",
      "La quantité doit être un nombre entier de titres (≥ 1)."
    );
}

export async function buy(ticker: string, quantity: number) {
  validateQuantity(quantity);
  if (!isTradable(ticker))
    throw new TradeError("UNKNOWN_TICKER", `Valeur inconnue ou non cotée : ${ticker}.`);

  const price = getLatestPrice(ticker)!;
  const { notional, fees, total } = buyCost(quantity, price);

  const portfolio = await getOrCreatePortfolio();
  if (total > portfolio.cash)
    throw new TradeError(
      "INSUFFICIENT_CASH",
      `Liquidités insuffisantes : besoin de ${Math.round(total)} FCFA, disponible ${Math.round(portfolio.cash)} FCFA.`
    );

  const cashAfter = portfolio.cash - total;

  return prisma.$transaction(async (tx) => {
    const existing = await tx.holding.findUnique({
      where: { portfolioId_ticker: { portfolioId: portfolio.id, ticker } },
    });

    if (existing) {
      const newQty = existing.quantity + quantity;
      // PRU pondéré, frais d'achat inclus dans le coût.
      const newAvg = (existing.quantity * existing.avgCost + total) / newQty;
      await tx.holding.update({
        where: { id: existing.id },
        data: { quantity: newQty, avgCost: newAvg },
      });
    } else {
      await tx.holding.create({
        data: {
          portfolioId: portfolio.id,
          ticker,
          quantity,
          avgCost: total / quantity,
        },
      });
    }

    await tx.portfolio.update({
      where: { id: portfolio.id },
      data: { cash: cashAfter },
    });

    return tx.transaction.create({
      data: {
        portfolioId: portfolio.id,
        type: "BUY",
        ticker,
        quantity,
        price,
        fees,
        cashDelta: -total,
        cashAfter,
      },
    });
  });
}

export async function sell(ticker: string, quantity: number) {
  validateQuantity(quantity);
  if (!isTradable(ticker))
    throw new TradeError("UNKNOWN_TICKER", `Valeur inconnue ou non cotée : ${ticker}.`);

  const portfolio = await getOrCreatePortfolio();
  const holding = await prisma.holding.findUnique({
    where: { portfolioId_ticker: { portfolioId: portfolio.id, ticker } },
  });

  // Pas de vente à découvert.
  if (!holding || holding.quantity < quantity)
    throw new TradeError(
      "INSUFFICIENT_SHARES",
      `Vente à découvert interdite : vous détenez ${holding?.quantity ?? 0} titre(s) de ${ticker}.`
    );

  const price = getLatestPrice(ticker)!;
  const { fees, total } = sellProceeds(quantity, price);
  const cashAfter = portfolio.cash + total;
  const newQty = holding.quantity - quantity;

  return prisma.$transaction(async (tx) => {
    if (newQty === 0) {
      await tx.holding.delete({ where: { id: holding.id } });
    } else {
      // Le PRU ne change pas lors d'une vente partielle.
      await tx.holding.update({
        where: { id: holding.id },
        data: { quantity: newQty },
      });
    }

    await tx.portfolio.update({
      where: { id: portfolio.id },
      data: { cash: cashAfter },
    });

    return tx.transaction.create({
      data: {
        portfolioId: portfolio.id,
        type: "SELL",
        ticker,
        quantity,
        price,
        fees,
        cashDelta: total,
        cashAfter,
      },
    });
  });
}

// --- Historique -----------------------------------------------------------

export async function getTransactions(limit = 200) {
  const portfolio = await getOrCreatePortfolio();
  return prisma.transaction.findMany({
    where: { portfolioId: portfolio.id },
    orderBy: { createdAt: "desc" },
    take: limit,
  });
}

/** Réinitialise le portefeuille (cash, positions, historique). */
export async function resetPortfolio() {
  const portfolio = await getOrCreatePortfolio();
  await prisma.$transaction([
    prisma.transaction.deleteMany({ where: { portfolioId: portfolio.id } }),
    prisma.holding.deleteMany({ where: { portfolioId: portfolio.id } }),
    prisma.portfolio.update({
      where: { id: portfolio.id },
      data: { cash: INITIAL_CASH },
    }),
  ]);
  if (INITIAL_CASH > 0) {
    await prisma.transaction.create({
      data: {
        portfolioId: portfolio.id,
        type: "DEPOSIT",
        fees: 0,
        cashDelta: INITIAL_CASH,
        cashAfter: INITIAL_CASH,
      },
    });
  }
  return getPortfolioSummary();
}
