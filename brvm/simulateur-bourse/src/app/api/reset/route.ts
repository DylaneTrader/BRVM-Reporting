import { NextResponse } from "next/server";
import { resetPortfolio } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

// POST /api/reset -> remet le portefeuille à zéro (cash initial, positions vidées).
export async function POST() {
  try {
    const summary = await resetPortfolio();
    return NextResponse.json({ summary });
  } catch (e) {
    return NextResponse.json(
      { error: "Réinitialisation impossible.", detail: String(e) },
      { status: 500 }
    );
  }
}
