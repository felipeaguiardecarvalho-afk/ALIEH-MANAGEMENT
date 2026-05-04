export function formatCurrency(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

/** Paridade com Streamlit `st.column_config.NumberColumn(format="%.2f")` em custo/preço de produtos. */
export function formatProductMoney(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value || 0);
}

/** Paridade com estoque em produtos no Streamlit (`format="%.4f"`). */
export function formatProductStock(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  }).format(value || 0);
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value || 0);
}

export function formatPercent(value: number) {
  return `${(value || 0).toFixed(1).replace(".", ",")}%`;
}

export function formatDate(value: string | null | undefined) {
  if (value == null || value === "") return "Sem data";
  const str = typeof value === "string" ? value : String(value);
  const date = new Date(str);
  if (Number.isNaN(date.getTime())) {
    return str.length >= 10 ? str.slice(0, 10) : str || "Sem data";
  }
  return new Intl.DateTimeFormat("pt-BR").format(date);
}
