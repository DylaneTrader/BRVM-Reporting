import { NextRequest, NextResponse } from "next/server";
import { getAlgoPortfolio, getDividendesAVenir, getSignal } from "@/lib/data";
import { getLatestPrice, getQuote } from "@/lib/market";
import { getPortfolioSummary } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

// GET /api/strategie?capital=2000000
// -> allocation cible Black-Litterman + plan d'action vs portefeuille actuel.
export async function GET(req: NextRequest) {
  const algo = getAlgoPortfolio();
  if (!algo)
    return NextResponse.json(
      { error: "Allocation algorithmique indisponible." },
      { status: 404 }
    );

  const summary = await getPortfolioSummary();
  const capitalParam = parseFloat(req.nextUrl.searchParams.get("capital") || "");
  const capital =
    Number.isFinite(capitalParam) && capitalParam > 0
      ? capitalParam
      : Math.max(summary.totalValue, 0);

  const heldBy: Record<string, number> = {};
  for (const p of summary.positions) heldBy[p.ticker] = p.quantity;

  const lines = Object.entries(algo.allocation)
    .map(([ticker, weight]) => {
      const price = getLatestPrice(ticker);
      const quote = getQuote(ticker);
      const targetValue = weight * capital;
      const targetShares = price ? Math.floor(targetValue / price) : 0;
      const currentShares = heldBy[ticker] ?? 0;
      const deltaShares = targetShares - currentShares;
      const signal = getSignal(ticker);
      return {
        ticker,
        code: ticker.split("_")[0],
        nom: quote?.nom || ticker,
        weight,
        price,
        targetValue,
        targetShares,
        currentShares,
        deltaShares,
        action: deltaShares > 0 ? "BUY" : deltaShares < 0 ? "SELL" : "HOLD",
        signal: signal?.signal ?? null,
        upside:
          signal && signal.last_price
            ? ((signal.target_30d - signal.last_price) / signal.last_price) * 100
            : null,
      };
    })
    .sort((a, b) => b.weight - a.weight);

  // Dividendes à venir concernant les valeurs de l'allocation cible.
  const targetTickers = new Set(Object.keys(algo.allocation));
  const dividendes = getDividendesAVenir().filter((d) =>
    targetTickers.has(d.ticker)
  );

  return NextResponse.json({
    generatedAt: algo.generated_at,
    horizonDays: algo.horizon_days,
    metrics: {
      expectedReturn30d: algo.expected_return_30d,
      expectedVolatility30d: algo.expected_volatility_30d,
      sharpe30d: algo.sharpe_ratio_30d,
    },
    capital,
    lines,
    dividendes,
  });
}
