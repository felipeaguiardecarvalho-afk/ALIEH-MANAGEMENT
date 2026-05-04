// Espelha `database/constants.py` e as listas de `app.py` sem duplicar regras de negócio.
// Valores gravados em BD permanecem idênticos aos usados pelo Streamlit.

export const FILTER_ANY = "Qualquer";

export const SALE_PAYMENT_OPTIONS = [
  "Dinheiro",
  "Pix",
  "Débito",
  "Crédito",
] as const;

export type SalePaymentOption = (typeof SALE_PAYMENT_OPTIONS)[number];

export const SKU_COST_COMPONENT_DEFINITIONS = [
  { key: "glasses", label: "Armação / lentes integradas" },
  { key: "purchase_packaging", label: "Embalagem de compra" },
  { key: "purchase_freight", label: "Frete de compra" },
  { key: "glasses_pouch", label: "Estojo / pouch" },
  { key: "retail_box", label: "Caixa de varejo" },
  { key: "cleaning_cloth", label: "Pano de limpeza" },
] as const;

export const PRODUCT_GENDER_OPTIONS = ["Masculino", "Feminino", "Unissex"];

export const PRODUCT_PALETTE_OPTIONS = [
  "Primavera",
  "Verão",
  "Outono",
  "Inverno",
];

export const PRODUCT_STYLE_OPTIONS = [
  "Aviador",
  "Wayfarer",
  "Redondo",
  "Retangular",
  "Gatinho",
  "Hexagonal",
  "Clubmaster",
  "Oval",
  "Esportivo",
];

export const PRODUCT_FRAME_COLOR_OPTIONS = [
  "Preto",
  "Preto / Fosco",
  "Preto / Brilhante",
  "Branco",
  "Branco / Pérola",
  "Marfim",
  "Creme",
  "Cinza",
  "Prata",
  "Dourado",
  "Ouro rose",
  "Cobre",
  "Bronze",
  "Champagne",
  "Azul-marinho",
  "Azul royal",
  "Verde",
  "Verde oliva",
  "Vermelho",
  "Bordô",
  "Rosa",
  "Magenta",
  "Roxo",
  "Marrom",
  "Bege / Cáqui claro",
  "Camel",
  "Café",
  "Amarelo",
  "Mostarda",
  "Laranja",
  "Tartaruga / Havana",
  "Havana",
  "Mel",
  "Cristal",
  "Transparente",
];

export const PRODUCT_LENS_COLOR_OPTIONS = [
  "Preto",
  "Cinza",
  "Marrom",
  "Verde",
  "Azul",
  "Degradê preto",
  "Degradê marrom",
  "Espelhado prata",
  "Espelhado azul",
  "Espelhado dourado",
  "Espelhado verde",
  "Amarelo",
];

export const UAT_STATUS_ORDER = [
  "pending",
  "pass",
  "fail",
  "blocked",
  "na",
] as const;

export type UatStatus = (typeof UAT_STATUS_ORDER)[number];

export const UAT_STATUS_LABELS: Record<UatStatus, string> = {
  pending: "Pendente",
  pass: "Passou",
  fail: "Falhou",
  blocked: "Bloqueado",
  na: "N/A",
};

// Casos manuais — extraídos de `database.repositories.uat_checklist_repository.UAT_MANUAL_CASES`.
export const UAT_MANUAL_CASES: { code: string; title: string; description: string }[] = [
  {
    code: "UAT-M-01",
    title: "Login administrador",
    description: "Login **admin** — sucesso; sidebar e páginas visíveis.",
  },
  {
    code: "UAT-M-02",
    title: "Login operador e restrição de páginas",
    description:
      "Login **operator** — sucesso; páginas **Precificação** e **Estoque** bloqueadas ou inacessíveis conforme política.",
  },
  {
    code: "UAT-M-03",
    title: "Venda completa como operador",
    description:
      "Como **operator**: registar **venda** completa (SKU, cliente, quantidade, pagamento) — sucesso e decremento de estoque.",
  },
  {
    code: "UAT-M-04",
    title: "Cadastro de produto",
    description: "Criar produto novo com atributos; SKU gerado e visível na busca.",
  },
  {
    code: "UAT-M-05",
    title: "Cadastro de cliente",
    description: "Cadastrar cliente com CEP; código sequencial alocado.",
  },
  {
    code: "UAT-M-06",
    title: "Entrada de estoque",
    description: "Aplicar entrada de estoque; custo médio e total de estoque no `sku_master` atualizam.",
  },
  {
    code: "UAT-M-07",
    title: "Precificação",
    description: "Salvar novo registro de precificação; preço ativo é propagado para `products.price`.",
  },
  {
    code: "UAT-M-08",
    title: "Baixa manual de estoque",
    description: "Baixa manual em lote reduz `products.stock` sem alterar custo/preço.",
  },
  {
    code: "UAT-M-09",
    title: "Exclusão de lote",
    description: "Excluir lote zera estoque e precificação do `product_enter_code` selecionado.",
  },
  {
    code: "UAT-M-10",
    title: "Checklist UAT persistente",
    description: "Resultado gravado aparece imediatamente na tabela resumo após refresh.",
  },
  {
    code: "UAT-M-11",
    title: "Tenant isolation",
    description: "Dados de um `tenant_id` não aparecem em sessões de outro `tenant_id`.",
  },
];
