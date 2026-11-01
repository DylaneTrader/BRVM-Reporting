import { BROKERAGE_FEE_RATE } from "./config";

/**
 * Frais de courtage simulés. La BRVM cumule en réalité plusieurs commissions
 * (courtage SGI, commission BRVM, DC/BR, taxe CREPMF). On les agrège ici en un
 * seul taux configurable, arrondi au FCFA entier.
 */
export function computeFees(notional: number, rate = BROKERAGE_FEE_RATE): number {
  return Math.round(notional * rate);
}

/** Coût total d'un achat de `quantity` titres à `price` (titres + frais). */
export function buyCost(quantity: number, price: number) {
  const notional = quantity * price;
  const fees = computeFees(notional);
  return { notional, fees, total: notional + fees };
}

/** Produit net d'une vente de `quantity` titres à `price` (titres - frais). */
export function sellProceeds(quantity: number, price: number) {
  const notional = quantity * price;
  const fees = computeFees(notional);
  return { notional, fees, total: notional - fees };
}
