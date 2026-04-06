"""Mensagens de erro de utilizador centralizadas (texto idêntico ao histórico da app)."""

from __future__ import annotations

# --- Validação de campos (produtos, custos, vendas) ---

MSG_QTY_MUST_BE_POSITIVE = "A quantidade deve ser maior que zero."
MSG_UNIT_COST_MUST_BE_POSITIVE = "O custo unitário deve ser maior que zero."
MSG_DISCOUNT_NON_NEGATIVE = "O desconto não pode ser negativo."
MSG_PAYMENT_METHOD_REQUIRED = "Informe a forma de pagamento."
MSG_PAYMENT_METHOD_INVALID = "Forma de pagamento inválida."
MSG_SKU_REQUIRED = "SKU é obrigatório."
MSG_LIST_PRICE_MUST_BE_POSITIVE = "O preço de venda deve ser maior que zero."
MSG_STOCK_REQUIRES_POSITIVE_UNIT_COST = (
    "Com estoque maior que zero, o custo unitário é obrigatório e deve ser maior que zero."
)
MSG_STOCK_CANNOT_BE_NEGATIVE = "O estoque não pode ser negativo."
MSG_MARGIN_TAXES_CHARGES_NON_NEGATIVE = (
    "Margem, impostos e encargos devem ser zero ou maiores."
)
MSG_COMPONENT_UNIT_PRICE_QTY_NON_NEGATIVE = (
    "Preço unitário e quantidade não podem ser negativos."
)
MSG_TARGET_PRICE_MUST_BE_POSITIVE = "O preço-alvo calculado deve ser maior que zero."
MSG_PRODUCT_NAME_REQUIRED = "O nome do produto é obrigatório."

# --- Clientes ---

MSG_CLIENT_NOT_FOUND = "Cliente não encontrado."


def format_customer_duplicate_identity(kind_label: str, customer_code, name) -> str:
    return (
        f"{kind_label} duplicado: "
        f"já usado pelo cliente {customer_code} — {name}."
    )


def format_customer_delete_has_sales(n: int) -> str:
    return (
        f"Não é possível excluir: há {n} venda(s) registrada(s) para este cliente."
    )


# --- Produtos / stock / SKU (serviços) ---

MSG_PRODUCT_LOT_NOT_FOUND = "Lote de produto não encontrado."
MSG_PRODUCT_SKU_MISMATCH_BATCH = "O SKU do produto não corresponde ao lote selecionado."
MSG_STOCK_RECEIPT_INACTIVE_LOT = (
    "Não é possível adicionar estoque a um lote inativo (excluído logicamente)."
)
MSG_STOCK_RECEIPT_INACTIVE_SKU = (
    "Não é possível adicionar estoque a um SKU inativo (excluído logicamente)."
)
MSG_SKU_NOT_IN_MASTER = "SKU não cadastrado no mestre de estoque."
MSG_CMP_NOT_AVAILABLE = (
    "O custo médio de estoque (CMP) não está disponível para este SKU. "
    "Registre entradas de estoque na página Custos para definir o CMP antes de precificar."
)
MSG_PRODUCT_NOT_FOUND = "Produto não encontrado."
MSG_SKU_NOT_IN_STOCK_LINE = (
    "SKU não encontrado no estoque. "
    "Cadastre um produto ou registre uma entrada de estoque primeiro."
)


def format_duplicate_sku_attr_conflict(new_sku: str) -> str:
    return (
        f"Seria criado um SKU duplicado `{new_sku}`. "
        "Ajuste o nome do produto ou os atributos para obter um SKU único."
    )


def format_sku_already_exists(sku: str) -> str:
    return (
        f"O SKU `{sku}` já existe (duplicado). "
        "Use outro nome de produto ou ajuste os atributos para o SKU ser único."
    )


# --- Vendas ---

MSG_SALE_PRODUCT_SKU_INACTIVE = (
    "Este produto/SKU está inativo (excluído logicamente) e não pode ser vendido."
)
MSG_SALE_PRODUCT_NO_SKU = "O produto não tem SKU; não é possível registrar a venda."
MSG_SALE_DEFINE_LIST_PRICE_FIRST = (
    "Defina um preço de venda para este SKU em Precificação antes de vender."
)


def format_insufficient_stock(stock: float) -> str:
    return f"Estoque insuficiente. Disponível: {stock}"


MSG_SALE_DISCOUNT_EXCEEDS_BASE = (
    "O desconto não pode exceder o valor base (preço unitário × quantidade)."
)

# --- Autenticação ---

MSG_LOGIN_INVALID = "Utilizador ou senha incorretos."


def format_access_requires_role(role: str) -> str:
    r = (role or "").strip()
    return f"Acesso negado: é necessário o perfil «{r}»."


def format_access_requires_one_of_roles(roles: tuple[str, ...]) -> str:
    labels = sorted({(r or "").strip() for r in roles if (r or "").strip()})
    joined = "», «".join(labels)
    return f"Acesso negado: é necessário um dos perfis «{joined}»."


def format_login_rate_limited_wait(remaining_seconds: int) -> str:
    """Mensagem quando o login foi bloqueado por excesso de tentativas (por utilizador)."""
    rem = max(0, int(remaining_seconds))
    minutes, secs = rem // 60, rem % 60
    if minutes >= 1:
        return (
            "Muitas tentativas de login falhadas. Por segurança, aguarde "
            f"{minutes} min e {secs} s antes de tentar novamente."
        )
    return (
        "Muitas tentativas de login falhadas. Por segurança, aguarde "
        f"{secs} segundo(s) antes de tentar novamente."
    )


MSG_AUTH_LEGACY_DISABLED_BY_DB_USERS = (
    "**Credenciais legacy ignoradas:** há utilizadores na tabela `users`, pelo que o login "
    "**só** aceita contas registadas na base de dados (não utilize ALIEH_AUTH_* nem "
    "`auth_username` / `auth_password` para validar — pode removê-los da configuração para "
    "evitar confusão)."
)

MSG_PRODUCTION_AUTH_NOT_CONFIGURED = """### O que aconteceu
Neste ambiente foi detetado como **produção ou deploy live**, mas não há forma válida de login:
falta **credencial legacy** (um par utilizador/senha na configuração) **e** não existe **nenhum
utilizador** na tabela `users` da base SQLite. A aplicação **não continua** até existir pelo menos
um destes modos, para evitar uso sem proteção.

### Como este ambiente é considerado “produção”
- `ALIEH_ENV=production` ou `prod` (variável de ambiente ou chave equivalente nos Streamlit Secrets), ou
- `ALIEH_PRODUCTION=true` ou `ALIEH_USE_BUSINESS_DB` (mesma ideia que força o uso de `business.db`), ou
- hospedagem Streamlit Community Cloud (`/mount/src/…`).

### O que configurar (escolha pelo menos um meio)

**A) Credencial única (modo legacy, só enquanto a tabela `users` estiver vazia)**  
- Variáveis de ambiente: `ALIEH_AUTH_USERNAME` e `ALIEH_AUTH_PASSWORD`, ou  
- Streamlit Secrets: `auth_username` e `auth_password`, ou secção `[auth]` com `username` e `password`.

**B) Utilizadores na base de dados (prioritário)**  
- Garantir que `init_db` já correu (tabela `users`).  
- Criar utilizadores com palavra-passe segura, por exemplo o script `scripts/create_alieh_user.py`
  no repositório (ou `INSERT` equivalente com `password_hash` gerado pela app).
- **Assim que existir pelo menos um utilizador em `users`, o login legacy deixa de ser usado**
  (evita conflito entre os dois modos).

Depois de configurar, recarregue a aplicação e inicie sessão no ecrã de login."""
