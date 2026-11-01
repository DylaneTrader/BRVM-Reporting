import { NextResponse } from "next/server";
import { getHeadlineIndices } from "@/lib/data";

export const dynamic = "force-dynamic";

// GET /api/indices -> indices BRVM (valeur + variation jour).
export async function GET() {
  return NextResponse.json({ indices: getHeadlineIndices() });
}
