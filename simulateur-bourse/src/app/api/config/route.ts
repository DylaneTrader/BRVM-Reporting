import { NextResponse } from "next/server";
import { BROKERAGE_FEE_RATE, INITIAL_CASH } from "@/lib/config";

export const dynamic = "force-dynamic";

// GET /api/config -> paramètres publics du simulateur (taux de frais, etc.).
export async function GET() {
  return NextResponse.json({
    feeRate: BROKERAGE_FEE_RATE,
    initialCash: INITIAL_CASH,
  });
}
