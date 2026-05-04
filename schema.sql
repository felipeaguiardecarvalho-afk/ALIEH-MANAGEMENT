-- =============================================================================
-- ALIEH management — schema PostgreSQL (Supabase)
-- Paridade com SQLite pós init_db / migrações multitenant e FKs para sku_master.
--
-- Tipos portáveis (sem BOOLEAN / REAL / FLOAT do lado SQL — só este triângulo):
--   TEXT      — strings, datas em ISO-8601, códigos.
--   NUMERIC   — dinheiro, stock, percentagens, epoch em locked_until (como no SQLite REAL).
--   BIGINT    — contagens, flags 0/1, chaves substitutas (FK), last_value dos contadores.
--   BIGSERIAL — PK autoincrementadas (equivalente a INTEGER PK no SQLite).
--
-- Todas as tabelas têm tenant_id NOT NULL (isolamento multi-inquilino).
-- FKs compostas (tenant_id, …) reforçam que filhos não cruzam inquilino.
--
-- Executar no SQL Editor do Supabase (base vazia). Revise extensões/políticas RLS à parte.
-- =============================================================================

-- Metadados globais do motor de migrações (não multi-tenant; ids únicos por script).
CREATE TABLE IF NOT EXISTS app_schema_migrations (
    id TEXT PRIMARY KEY
);

-- ---------------------------------------------------------------------------
-- Núcleo: produtos e mestre de SKU (PK composta no mestre)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          TEXT NOT NULL DEFAULT 'default',
    name               TEXT NOT NULL,
    sku                TEXT,
    registered_date    TEXT,
    product_enter_code TEXT,
    cost               NUMERIC NOT NULL,
    price              NUMERIC NOT NULL,
    pricing_locked     BIGINT NOT NULL DEFAULT 0
        CHECK (pricing_locked IN (0, 1)),
    stock              NUMERIC NOT NULL
        CHECK (stock >= 0),
    frame_color        TEXT,
    lens_color         TEXT,
    style              TEXT,
    palette            TEXT,
    gender             TEXT,
    deleted_at         TEXT,
    created_at         TEXT,
    product_image_path TEXT,
    UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_products_sku ON products (sku);
CREATE INDEX IF NOT EXISTS idx_products_name ON products (name);
CREATE INDEX IF NOT EXISTS idx_products_tenant_sku ON products (tenant_id, sku);

CREATE TABLE IF NOT EXISTS sku_master (
    tenant_id             TEXT NOT NULL DEFAULT 'default',
    sku                   TEXT NOT NULL,
    total_stock           NUMERIC NOT NULL DEFAULT 0,
    avg_unit_cost         NUMERIC NOT NULL DEFAULT 0,
    selling_price         NUMERIC NOT NULL DEFAULT 0,
    structured_cost_total NUMERIC NOT NULL DEFAULT 0,
    updated_at            TEXT,
    deleted_at            TEXT,
    PRIMARY KEY (tenant_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_sku_master_tenant_deleted
    ON sku_master (tenant_id)
    WHERE deleted_at IS NULL;

-- ---------------------------------------------------------------------------
-- Clientes e utilizadores (multi-tenant)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      TEXT NOT NULL DEFAULT 'default',
    customer_code  TEXT NOT NULL,
    name           TEXT NOT NULL,
    cpf            TEXT,
    rg             TEXT,
    phone          TEXT,
    email          TEXT,
    instagram      TEXT,
    zip_code       TEXT,
    street         TEXT,
    number         TEXT,
    neighborhood   TEXT,
    city           TEXT,
    state          TEXT,
    country        TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT,
    UNIQUE (tenant_id, customer_code),
    UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_customers_tenant_code ON customers (tenant_id, customer_code);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers (name);

CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     TEXT NOT NULL DEFAULT 'default',
    username      TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'operator'
);

-- Case-insensitive unicidade do login (equivalente a COLLATE NOCASE no SQLite)
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_tenant_username_lower
    ON users (tenant_id, lower(username));

CREATE INDEX IF NOT EXISTS idx_users_tenant_username ON users (tenant_id, username);

-- ---------------------------------------------------------------------------
-- Contadores de sequência por tenant
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sku_sequence_counter (
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    id          BIGINT NOT NULL CHECK (id = 1),
    last_value  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS customer_sequence_counter (
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    id          BIGINT NOT NULL CHECK (id = 1),
    last_value  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS sale_sequence_counter (
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    id          BIGINT NOT NULL CHECK (id = 1),
    last_value  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, id)
);

-- ---------------------------------------------------------------------------
-- Histórico de preço, componentes de custo, pricing workflow
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_history (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL DEFAULT 'default',
    sku        TEXT NOT NULL,
    old_price  NUMERIC,
    new_price  NUMERIC NOT NULL,
    created_at TEXT NOT NULL,
    note       TEXT,
    FOREIGN KEY (tenant_id, sku) REFERENCES sku_master (tenant_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_price_history_tenant_sku ON price_history (tenant_id, sku);

CREATE TABLE IF NOT EXISTS sku_cost_components (
    tenant_id     TEXT NOT NULL DEFAULT 'default',
    sku           TEXT NOT NULL,
    component_key TEXT NOT NULL,
    label         TEXT NOT NULL,
    unit_price    NUMERIC NOT NULL DEFAULT 0
        CHECK (unit_price >= 0),
    quantity      NUMERIC NOT NULL DEFAULT 0
        CHECK (quantity >= 0),
    line_total    NUMERIC NOT NULL DEFAULT 0
        CHECK (line_total >= 0),
    updated_at    TEXT,
    PRIMARY KEY (tenant_id, sku, component_key),
    FOREIGN KEY (tenant_id, sku) REFERENCES sku_master (tenant_id, sku)
);

CREATE TABLE IF NOT EXISTS sku_pricing_records (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          TEXT NOT NULL DEFAULT 'default',
    sku                TEXT NOT NULL,
    avg_cost_snapshot  NUMERIC NOT NULL,
    markup_pct         NUMERIC NOT NULL CHECK (markup_pct >= 0),
    taxes_pct          NUMERIC NOT NULL CHECK (taxes_pct >= 0),
    interest_pct       NUMERIC NOT NULL CHECK (interest_pct >= 0),
    price_before_taxes NUMERIC NOT NULL,
    price_with_taxes   NUMERIC NOT NULL,
    target_price       NUMERIC NOT NULL,
    created_at         TEXT NOT NULL,
    is_active          BIGINT NOT NULL DEFAULT 0
        CHECK (is_active IN (0, 1)),
    markup_kind        BIGINT NOT NULL DEFAULT 0,
    taxes_kind         BIGINT NOT NULL DEFAULT 0,
    interest_kind      BIGINT NOT NULL DEFAULT 0,
    FOREIGN KEY (tenant_id, sku) REFERENCES sku_master (tenant_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_sku_pricing_records_sku ON sku_pricing_records (sku);
CREATE INDEX IF NOT EXISTS idx_sku_pricing_records_tenant_sku
    ON sku_pricing_records (tenant_id, sku);

-- ---------------------------------------------------------------------------
-- Movimentos de stock custeio
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_cost_entries (
    id                BIGSERIAL PRIMARY KEY,
    tenant_id         TEXT NOT NULL DEFAULT 'default',
    sku               TEXT NOT NULL,
    product_id        BIGINT,
    quantity          NUMERIC NOT NULL CHECK (quantity > 0),
    unit_cost         NUMERIC NOT NULL,
    total_entry_cost  NUMERIC NOT NULL,
    stock_before      NUMERIC NOT NULL,
    stock_after       NUMERIC NOT NULL,
    avg_cost_before   NUMERIC NOT NULL,
    avg_cost_after    NUMERIC NOT NULL,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id),
    FOREIGN KEY (tenant_id, sku) REFERENCES sku_master (tenant_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_stock_cost_tenant_sku ON stock_cost_entries (tenant_id, sku);

-- ---------------------------------------------------------------------------
-- Vendas
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sales (
    id               BIGSERIAL PRIMARY KEY,
    tenant_id        TEXT NOT NULL DEFAULT 'default',
    product_id       BIGINT NOT NULL,
    quantity         BIGINT NOT NULL CHECK (quantity >= 1),
    total            NUMERIC NOT NULL,
    sold_at          TEXT NOT NULL,
    cogs_total       NUMERIC NOT NULL DEFAULT 0,
    sku              TEXT,
    sale_code        TEXT,
    customer_id      BIGINT,
    unit_price       NUMERIC,
    discount_amount  NUMERIC NOT NULL DEFAULT 0,
    base_amount      NUMERIC,
    payment_method   TEXT,
    FOREIGN KEY (tenant_id, product_id) REFERENCES products (tenant_id, id),
    FOREIGN KEY (tenant_id, customer_id) REFERENCES customers (tenant_id, id),
    FOREIGN KEY (tenant_id, sku) REFERENCES sku_master (tenant_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_sales_tenant_sold_at ON sales (tenant_id, sold_at);
CREATE INDEX IF NOT EXISTS idx_sales_tenant_sku ON sales (tenant_id, sku);
-- Recent sales list: ORDER BY id DESC per tenant (api-prototype / Streamlit).
CREATE INDEX IF NOT EXISTS idx_sales_tenant_id_desc ON sales (tenant_id, id DESC);

-- ---------------------------------------------------------------------------
-- Auditoria / UAT
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sku_deletion_audit (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL DEFAULT 'default',
    sku        TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    deleted_by TEXT,
    note       TEXT
);

CREATE INDEX IF NOT EXISTS idx_sku_deletion_audit_tenant ON sku_deletion_audit (tenant_id);

CREATE TABLE IF NOT EXISTS login_user_throttle (
    tenant_id      TEXT NOT NULL DEFAULT 'default',
    username_norm  TEXT NOT NULL,
    failure_count  BIGINT NOT NULL DEFAULT 0,
    locked_until   NUMERIC NOT NULL DEFAULT 0,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (tenant_id, username_norm)
);

CREATE TABLE IF NOT EXISTS login_attempt_audit (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     TEXT NOT NULL DEFAULT 'default',
    username_norm TEXT NOT NULL,
    success       BIGINT NOT NULL CHECK (success IN (0, 1)),
    created_at    TEXT NOT NULL,
    client_hint   TEXT
);

CREATE INDEX IF NOT EXISTS idx_login_audit_username ON login_attempt_audit (username_norm);
CREATE INDEX IF NOT EXISTS idx_login_audit_created ON login_attempt_audit (created_at);
CREATE INDEX IF NOT EXISTS idx_login_audit_tenant ON login_attempt_audit (tenant_id);

CREATE TABLE IF NOT EXISTS uat_manual_checklist (
    id                     BIGSERIAL PRIMARY KEY,
    tenant_id              TEXT NOT NULL DEFAULT 'default',
    test_id                TEXT NOT NULL,
    status                 TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'pass', 'fail', 'blocked', 'na')),
    notes                  TEXT,
    result_recorded_at     TEXT,
    recorded_by_username   TEXT,
    recorded_by_user_id    TEXT,
    recorded_by_role       TEXT,
    updated_at             TEXT NOT NULL,
    UNIQUE (tenant_id, test_id)
);

CREATE INDEX IF NOT EXISTS idx_uat_checklist_tenant ON uat_manual_checklist (tenant_id);

-- ---------------------------------------------------------------------------
-- Imutabilidade de linhas de auditoria (equivalente aos triggers SQLite)
-- Requer PostgreSQL 14+ (EXECUTE FUNCTION). Em 13, troque por EXECUTE PROCEDURE.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION forbid_login_attempt_audit_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'login_attempt_audit: DELETE não permitido (auditoria).';
END;
$$;

CREATE OR REPLACE FUNCTION forbid_login_attempt_audit_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'login_attempt_audit: UPDATE não permitido (auditoria).';
END;
$$;

DROP TRIGGER IF EXISTS tr_login_attempt_audit_no_delete ON login_attempt_audit;
CREATE TRIGGER tr_login_attempt_audit_no_delete
    BEFORE DELETE ON login_attempt_audit
    FOR EACH ROW
    EXECUTE FUNCTION forbid_login_attempt_audit_delete();

DROP TRIGGER IF EXISTS tr_login_attempt_audit_no_update ON login_attempt_audit;
CREATE TRIGGER tr_login_attempt_audit_no_update
    BEFORE UPDATE ON login_attempt_audit
    FOR EACH ROW
    EXECUTE FUNCTION forbid_login_attempt_audit_update();

CREATE OR REPLACE FUNCTION forbid_sku_deletion_audit_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'sku_deletion_audit: DELETE não permitido (auditoria).';
END;
$$;

CREATE OR REPLACE FUNCTION forbid_sku_deletion_audit_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'sku_deletion_audit: UPDATE não permitido (auditoria).';
END;
$$;

DROP TRIGGER IF EXISTS tr_sku_deletion_audit_no_delete ON sku_deletion_audit;
CREATE TRIGGER tr_sku_deletion_audit_no_delete
    BEFORE DELETE ON sku_deletion_audit
    FOR EACH ROW
    EXECUTE FUNCTION forbid_sku_deletion_audit_delete();

DROP TRIGGER IF EXISTS tr_sku_deletion_audit_no_update ON sku_deletion_audit;
CREATE TRIGGER tr_sku_deletion_audit_no_update
    BEFORE UPDATE ON sku_deletion_audit
    FOR EACH ROW
    EXECUTE FUNCTION forbid_sku_deletion_audit_update();

-- ---------------------------------------------------------------------------
-- Sementes mínimas dos contadores (opcional; alinhar ao SQLite init)
-- ---------------------------------------------------------------------------
INSERT INTO sku_sequence_counter (tenant_id, id, last_value)
VALUES ('default', 1, 0)
ON CONFLICT (tenant_id, id) DO NOTHING;

INSERT INTO customer_sequence_counter (tenant_id, id, last_value)
VALUES ('default', 1, 0)
ON CONFLICT (tenant_id, id) DO NOTHING;

INSERT INTO sale_sequence_counter (tenant_id, id, last_value)
VALUES ('default', 1, 0)
ON CONFLICT (tenant_id, id) DO NOTHING;
