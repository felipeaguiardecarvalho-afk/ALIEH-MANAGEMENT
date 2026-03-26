"""
Página: Produtos.

Cadastro de lotes (produtos), busca por SKU, sequência do prefixo numérico do SKU
e auditoria opcional de exclusão de SKU.
"""

TABLES = (
    "products",
    "sku_sequence_counter",
    "sku_deletion_audit",
)

KEY_COLUMNS_PRODUCTS = (
    "id",
    "name",
    "sku",
    "registered_date",
    "product_enter_code",
    "cost",
    "price",
    "pricing_locked",
    "stock",
    "frame_color",
    "lens_color",
    "style",
    "palette",
    "gender",
    "deleted_at",
    "created_at",
)
