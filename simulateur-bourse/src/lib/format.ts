/** Formatage FCFA : entier avec séparateur de milliers + " FCFA". */
export function formatFCFA(value: number, decimals = 0): string {
  const v = Number.isFinite(value) ? value : 0;
  return (
    v.toLocaleString("fr-FR", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }) + " FCFA"
  );
}

/** Nombre simple formaté FR (titres, quantités). */
export function formatNumber(value: number): string {
  return (Number.isFinite(value) ? value : 0).toLocaleString("fr-FR");
}

/** Pourcentage signé : +3,21 % / -1,05 %. */
export function formatPct(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return (
    sign +
    value.toLocaleString("fr-FR", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }) +
    " %"
  );
}

/** Classe Tailwind selon le signe (gain / loss / neutre). */
export function pnlClass(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value === 0)
    return "text-slate-400";
  return value > 0 ? "text-gain" : "text-loss";
}
