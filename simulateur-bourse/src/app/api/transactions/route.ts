import { NextRequest, NextResponse } from "next/server";
import { getTransactions } from "@/lib/portfolio";

export const dynamic = "force-dynamic";

// GET /api/transactions?limit=200 -> historique des opérations.
export async function GET(req: NextRequest) {
  const limit = parseInt(req.nextUrl.searchParams.get("limit") || "200", 10);
  const transactions = await getTransactions(limit);
  return NextResponse.json({ transactions });
}
