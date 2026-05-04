"""Payloads mínimos para rotas de venda (apenas estrutura; IDs reais vêm do ambiente)."""


def minimal_preview_body(*, product_id: int = 1, customer_id: int = 1) -> dict:
    return {
        "product_id": product_id,
        "quantity": 1,
        "customer_id": customer_id,
        "discount_mode": "percent",
        "discount_input": 0.0,
        "payment_method": "Dinheiro",
    }
