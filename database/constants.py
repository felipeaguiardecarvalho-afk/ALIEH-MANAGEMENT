"""Constantes compartilhadas pelo banco e pelo app."""

# Busca de produtos — valor do filtro “não restringir atributo”.
FILTER_ANY = "Qualquer"

# Vendas — forma de pagamento (valor gravado em `sales.payment_method`)
SALE_PAYMENT_OPTIONS = ("Dinheiro", "Pix", "Débito", "Crédito")

# Bloqueio de cadastro/edição quando já existe produto com o mesmo corpo de SKU (sem prefixo SEQ).
DUPLICATE_SKU_BASE_ERROR_MSG = "Produto já cadastrado na base."

# Composição de custo do SKU (rótulos exibidos; chave estável permanece em inglês)
SKU_COST_COMPONENT_DEFINITIONS = [
    ("glasses", "Armação / lentes integradas"),
    ("purchase_packaging", "Embalagem de compra"),
    ("purchase_freight", "Frete de compra"),
    ("glasses_pouch", "Estojo / pouch"),
    ("retail_box", "Caixa de varejo"),
    ("cleaning_cloth", "Pano de limpeza"),
]
