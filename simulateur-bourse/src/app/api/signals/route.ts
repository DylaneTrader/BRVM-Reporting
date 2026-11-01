import { NextResponse } from "next/server";
import { getSignalsPayload, signalUpside } from "@/lib/data";

export const dynamic = "force-dynamic";

// GET /api/signals -> signaux Prophet (par valeur) + diagnostic de concentration.
export async function GET() {
  const payload = getSignalsPayload();
  if (!payload)
    return NextResponse.json({ signals: {}, meta: null, items: [] });

  // Liste triée par potentiel 30j décroissant (pratique côté UI).
  const items = Object.values(payload.signals)
    .map((s) => ({ ...s, upside: signalUpside(s) }))
    .sort((a, b) => (b.upside ?? -999) - (a.upside ?? -999));

  return NextResponse.json({
    signals: payload.signals,
    items,
    meta: {
      as_of: payload.as_of,
      horizon_days: payload.horizon_days,
      concentration: payload.concentration_diagnostic,
    },
  });
}
