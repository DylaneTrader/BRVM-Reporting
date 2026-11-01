import { NextResponse } from "next/server";
import { getPortfolioSummary } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

// GET /api/portfolio -> synthèse du portefeuille (cash, positions, P&L).
export async function GET() {
  try {
    const summary = await getPortfolioSummary();
    return NextResponse.json(summary);
  } catch (e) {
    return NextResponse.json(
      { error: "Erreur de lecture du portefeuille.", detail: String(e) },
      { status: 500 }
    );
  }
}
