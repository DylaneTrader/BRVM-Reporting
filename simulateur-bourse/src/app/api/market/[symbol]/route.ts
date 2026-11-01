import { NextRequest, NextResponse } from "next/server";
import { getQuote, getHistory, getSociete } from "@/lib/market";
import { getSignal, getFondamentaux, getDividendesAVenir } from "@/lib/data";

export const dynamic = "force-dynamic";

// GET /api/market/[symbol]?history=120
// -> cotation + fiche société + historique + signal Prophet + fondamentaux + dividende à venir.
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const quote = getQuote(symbol);
  if (!quote)
    return NextResponse.json(
      { error: `Valeur inconnue : ${symbol}` },
      { status: 404 }
    );

  const limit = parseInt(req.nextUrl.searchParams.get("history") || "120", 10);
  const full = getHistory(symbol);
  const history = limit > 0 ? full.slice(-limit) : full;

  const dividende =
    getDividendesAVenir().find((d) => d.ticker === symbol) ?? null;

  return NextResponse.json({
    quote,
    societe: getSociete(symbol),
    signal: getSignal(symbol),
    fondamentaux: getFondamentaux(symbol),
    dividende,
    history,
  });
}
