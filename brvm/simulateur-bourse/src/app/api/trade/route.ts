import { NextRequest, NextResponse } from "next/server";
import { buy, sell, TradeError, getPortfolioSummary } from "@/lib/portfolio";
import { getQuote } from "@/lib/market";
import { buyCost, sellProceeds } from "@/lib/fees";

export const dynamic = "force-dynamic";

// GET /api/trade?symbol=SGBC_ci&side=buy&quantity=10
// -> aperçu (prix, frais, total) sans exécuter. Pour la confirmation côté UI.
export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol") || "";
  const side = req.nextUrl.searchParams.get("side") || "buy";
  const quantity = parseInt(req.nextUrl.searchParams.get("quantity") || "0", 10);
  const quote = getQuote(symbol);
  if (!quote)
    return NextResponse.json({ error: `Valeur inconnue : ${symbol}` }, { status: 404 });
  if (!Number.isInteger(quantity) || quantity < 1)
    return NextResponse.json({ quote, preview: null });

  const preview =
    side === "sell"
      ? sellProceeds(quantity, quote.price)
      : buyCost(quantity, quote.price);
  return NextResponse.json({ quote, side, quantity, preview });
}

// POST /api/trade  { symbol, side: "buy" | "sell", quantity }
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const symbol = String(body?.symbol || "");
    const side = body?.side;
    const quantity = Number(body?.quantity);

    if (side !== "buy" && side !== "sell")
      return NextResponse.json(
        { error: "side doit être 'buy' ou 'sell'." },
        { status: 400 }
      );

    const tx = side === "buy" ? await buy(symbol, quantity) : await sell(symbol, quantity);
    const summary = await getPortfolioSummary();
    return NextResponse.json({ transaction: tx, summary });
  } catch (e) {
    if (e instanceof TradeError)
      return NextResponse.json({ error: e.message, code: e.code }, { status: 400 });
    return NextResponse.json(
      { error: "Erreur lors de l'ordre.", detail: String(e) },
      { status: 500 }
    );
  }
}
