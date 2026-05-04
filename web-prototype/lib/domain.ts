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
