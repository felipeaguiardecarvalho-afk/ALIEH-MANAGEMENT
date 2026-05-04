// Espelho de `services.product_service.compute_sku_pricing_targets` (mesma fórmula e `round(..., 2)`).
// A UI de `/pricing` usa **só** `POST /pricing/sku/compute-targets` para preview e validação — esta função
// permanece para testes, importações pontuais e documentação da paridade numérica.
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
