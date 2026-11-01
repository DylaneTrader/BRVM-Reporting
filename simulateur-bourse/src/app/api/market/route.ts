import { NextResponse } from "next/server";
import { getAllQuotes } from "@/lib/market";

export const dynamic = "force-dynamic";

// GET /api/market -> liste de toutes les cotations BRVM.
export async function GET() {
  try {
    const quotes = getAllQuotes();
    return NextResponse.json({ quotes, count: quotes.length });
  } catch (e) {
    return NextResponse.json(
      { error: "Lecture des données de marché impossible.", detail: String(e) },
      { status: 500 }
    );
  }
}
