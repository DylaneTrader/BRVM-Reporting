"use client";

/** Badge coloré pour un signal Prophet (ACHAT / VENTE / NEUTRE). */
export function SignalBadge({
  signal,
  confidence,
  size = "sm",
}: {
  signal: string | null | undefined;
  confidence?: string;
  size?: "sm" | "md";
}) {
  if (!signal) return <span className="text-slate-600">—</span>;
  const s = signal.toUpperCase();
  const style =
    s === "ACHAT"
      ? "bg-emerald-600/20 text-emerald-300 border-emerald-600/30"
      : s === "VENTE"
      ? "bg-rose-600/20 text-rose-300 border-rose-600/30"
      : "bg-slate-600/20 text-slate-300 border-slate-600/30";
  const pad = size === "md" ? "px-2.5 py-1 text-xs" : "px-2 py-0.5 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border font-semibold ${style} ${pad}`}
    >
      {s}
      {confidence && <span className="font-normal opacity-70">· {confidence}</span>}
    </span>
  );
}
