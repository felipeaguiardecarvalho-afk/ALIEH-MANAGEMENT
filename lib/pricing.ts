// Espelho fiel de `services.product_service.compute_sku_pricing_targets`.
// Não altera regras — apenas reexpressa a fórmula em TS para cálculo live no cliente/server.
// Modo 0 = percentual (valor em %), modo 1 = absoluto (R$).

export type PricingKind = 0 | 1;

export function computePricingTargets(
  avgCost: number,
  markupVal: number,
  taxesVal: number,
  interestVal: number,
  {
    markupKind = 0,
    taxesKind = 0,
    interestKind = 0,
  }: {
    markupKind?: PricingKind;
    taxesKind?: PricingKind;
    interestKind?: PricingKind;
  } = {}
) {
  const avg = Number(avgCost) || 0;
  const priceBefore =
    markupKind === 1 ? avg + markupVal : avg + avg * (markupVal / 100);
  const priceWithTaxes =
    taxesKind === 1 ? priceBefore + taxesVal : priceBefore + priceBefore * (taxesVal / 100);
  const target =
    interestKind === 1
      ? priceWithTaxes + interestVal
      : priceWithTaxes + priceWithTaxes * (interestVal / 100);
  return {
    priceBefore: round2(priceBefore),
    priceWithTaxes: round2(priceWithTaxes),
    targetPrice: round2(target),
  };
}

function round2(value: number) {
  return Math.round(value * 100) / 100;
}
