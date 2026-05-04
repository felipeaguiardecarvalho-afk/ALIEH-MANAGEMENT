/** Paridade com `utils.formatters.format_qty_display_4` (Streamlit Custos). */
export function formatQtyDisplay4(q: number): string {
  const v = Math.round((Number(q) || 0) * 10000) / 10000;
  if (Math.abs(v) < 1e-12) return "";
  const s = `${v.toFixed(4)}`.replace(/\.?0+$/, "");
  return s || "0";
}
