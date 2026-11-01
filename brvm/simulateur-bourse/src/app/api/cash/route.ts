import { NextRequest, NextResponse } from "next/server";
import { deposit, withdraw, TradeError, getPortfolioSummary } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

// POST /api/cash  { action: "deposit" | "withdraw", amount: number }
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const action = body?.action;
    const amount = Number(body?.amount);

    if (action !== "deposit" && action !== "withdraw")
      return NextResponse.json(
        { error: "action doit être 'deposit' ou 'withdraw'." },
        { status: 400 }
      );

    const tx = action === "deposit" ? await deposit(amount) : await withdraw(amount);
    const summary = await getPortfolioSummary();
    return NextResponse.json({ transaction: tx, summary });
  } catch (e) {
    if (e instanceof TradeError)
      return NextResponse.json({ error: e.message, code: e.code }, { status: 400 });
    return NextResponse.json(
      { error: "Erreur sur l'opération de liquidités.", detail: String(e) },
      { status: 500 }
    );
  }
}
