import "server-only";
import { unstable_cache } from "next/cache";
import { db, getTenantId, hasDatabaseUrl } from "@/lib/db";
import type {
  ActivePricingRecord,
  Customer,
  DailyRevenue,
  DashboardKpis,
  InventoryItem,
  Product,
  ProductBatch,
  SaleableSku,
  Sale,
  SkuCostComponent,
  SkuMasterRow,
} from "@/lib/types";

const REVALIDATE_SECONDS = 120;

// ---------- mock fallback ----------

const mockProducts: Product[] = [
  {
    id: 101,
    name: "ALIEH Noir Cat Eye",
    sku: "01-CE-PR-FU-FE-NO-GA",
    registeredDate: "2026-04-12",
    productEnterCode: "aliehnoir-2026-04-12",
    cost: 118,
    price: 389,
    pricingLocked: true,
    stock: 14,
    frameColor: "Preto",
    lensColor: "Fumê",
    style: "Gatinho",
    palette: "Noir",
    gender: "Feminino",
  },
  {
    id: 102,
    name: "ALIEH Gold Aviator",
    sku: "02-AV-DO-MA-UN-CH-AV",
    registeredDate: "2026-04-18",
    productEnterCode: "aliehgold-2026-04-18",
    cost: 132,
    price: 449,
    pricingLocked: false,
    stock: 7,
    frameColor: "Dourado",
    lensColor: "Marrom",
    style: "Aviador",
    palette: "Champagne",
    gender: "Unissex",
  },
  {
    id: 103,
    name: "ALIEH Ivory Square",
    sku: "03-RE-MA-VE-UN-PE-QU",
    registeredDate: "2026-04-24",
    productEnterCode: "aliehivory-2026-04-24",
    cost: 96,
    price: 329,
    pricingLocked: true,
    stock: 22,
    frameColor: "Marfim",
    lensColor: "Verde",
    style: "Retangular",
    palette: "Pérola",
    gender: "Unissex",
  },
];

const mockCustomers: Customer[] = [
  {
    id: 1,
    customerCode: "C0001",
    name: "Marina Costa",
    cpf: "123.456.789-00",
    rg: null,
    phone: "(11) 98888-1100",
    email: "marina@example.com",
    instagram: "@marinacosta",
    zipCode: "01310-100",
    street: "Av. Paulista",
    number: "1500",
    neighborhood: "Bela Vista",
    city: "São Paulo",
    state: "SP",
    country: "Brasil",
    createdAt: "2026-04-03",
  },
  {
    id: 2,
    customerCode: "C0002",
    name: "Rafael Nunes",
    cpf: null,
    rg: null,
    phone: "(21) 97777-2211",
    email: "rafael@example.com",
    instagram: null,
    zipCode: "22071-000",
    street: "Av. Atlântica",
    number: "4000",
    neighborhood: "Copacabana",
    city: "Rio de Janeiro",
    state: "RJ",
    country: "Brasil",
    createdAt: "2026-04-09",
  },
];

const mockSales: Sale[] = [
  {
    id: 301,
    saleCode: "00001V",
    sku: "01-CE-PR-FU-FE-NO-GA",
    quantity: 2,
    total: 778,
    profit: 542,
    soldAt: "2026-04-28",
    paymentMethod: "Crédito",
    customerId: 1,
  },
  {
    id: 302,
    saleCode: "00002V",
    sku: "03-RE-MA-VE-UN-PE-Qu",
    quantity: 1,
    total: 329,
    profit: 233,
    soldAt: "2026-04-30",
    paymentMethod: "Pix",
    customerId: 2,
  },
];

function safeNumber(value: unknown) {
  return Number(value || 0);
}

function logFallback(scope: string, error: unknown) {
  if (process.env.NODE_ENV !== "production") {
    console.warn(`[mock fallback] ${scope}:`, error);
  }
}

function getDateWindow(days = 30) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - days);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

// ---------- dashboard ----------

async function queryDashboardKpis(tenantId: string): Promise<DashboardKpis> {
  if (!hasDatabaseUrl) return mockDashboardKpis();

  try {
    const sql = db();
    const { start, end } = getDateWindow(30);
    const [kpi] = await sql`
      SELECT
        COALESCE(SUM(s.total), 0) AS revenue,
        COALESCE(SUM(s.cogs_total), 0) AS cost,
        COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit,
        COUNT(*) AS sales_count,
        COUNT(DISTINCT s.customer_id) AS unique_customers
      FROM sales s
      WHERE s.tenant_id = ${tenantId}
        AND substr(s.sold_at, 1, 10) >= ${start}
        AND substr(s.sold_at, 1, 10) <= ${end};
    `;
    const [stock] = await sql`
      SELECT COALESCE(SUM(stock), 0) AS stock_units
      FROM products
      WHERE tenant_id = ${tenantId}
        AND deleted_at IS NULL;
    `;
    const revenue = safeNumber(kpi?.revenue);
    const profit = safeNumber(kpi?.profit);
    const salesCount = safeNumber(kpi?.sales_count);

    return {
      revenue,
      cost: safeNumber(kpi?.cost),
      profit,
      marginPct: revenue > 0 ? (profit / revenue) * 100 : 0,
      salesCount,
      uniqueCustomers: safeNumber(kpi?.unique_customers),
      ticketAvg: salesCount > 0 ? revenue / salesCount : 0,
      stockUnits: safeNumber(stock?.stock_units),
    };
  } catch (error) {
    logFallback("dashboard KPIs", error);
    return mockDashboardKpis();
  }
}

function mockDashboardKpis(): DashboardKpis {
  const revenue = mockSales.reduce((sum, sale) => sum + sale.total, 0);
  const profit = mockSales.reduce((sum, sale) => sum + sale.profit, 0);
  const salesCount = mockSales.length;

  return {
    revenue,
    cost: revenue - profit,
    profit,
    marginPct: revenue > 0 ? (profit / revenue) * 100 : 0,
    salesCount,
    uniqueCustomers: mockCustomers.length,
    ticketAvg: salesCount > 0 ? revenue / salesCount : 0,
    stockUnits: mockProducts.reduce((sum, product) => sum + product.stock, 0),
  };
}

export const getDashboardKpis = unstable_cache(
  async (tenantId = getTenantId()) => queryDashboardKpis(tenantId),
  ["dashboard-kpis"],
  { revalidate: REVALIDATE_SECONDS }
);

export const getDailyRevenue = unstable_cache(
  async (tenantId = getTenantId()): Promise<DailyRevenue[]> => {
    if (!hasDatabaseUrl) {
      return mockSales.map((sale) => ({
        day: sale.soldAt,
        revenue: sale.total,
        profit: sale.profit,
      }));
    }

    try {
      const sql = db();
      const { start, end } = getDateWindow(30);
      const rows = await sql`
        SELECT
          substr(s.sold_at, 1, 10) AS day,
          COALESCE(SUM(s.total), 0) AS revenue,
          COALESCE(SUM(s.total - COALESCE(s.cogs_total, 0)), 0) AS profit
        FROM sales s
        WHERE s.tenant_id = ${tenantId}
          AND substr(s.sold_at, 1, 10) >= ${start}
          AND substr(s.sold_at, 1, 10) <= ${end}
        GROUP BY day
        ORDER BY day;
      `;
      return rows.map((row) => ({
        day: String(row.day),
        revenue: safeNumber(row.revenue),
        profit: safeNumber(row.profit),
      }));
    } catch (error) {
      logFallback("daily revenue", error);
      return mockSales.map((sale) => ({
        day: sale.soldAt,
        revenue: sale.total,
        profit: sale.profit,
      }));
    }
  },
  ["daily-revenue"],
  { revalidate: REVALIDATE_SECONDS }
);

// ---------- products ----------

export const getProducts = unstable_cache(
  async (tenantId = getTenantId()): Promise<Product[]> => {
    if (!hasDatabaseUrl) return mockProducts;

    try {
      const rows = await db()`
        SELECT id, name, sku, registered_date, product_enter_code, cost, price,
               pricing_locked, stock, frame_color, lens_color, style, palette, gender
        FROM products
        WHERE tenant_id = ${tenantId}
          AND deleted_at IS NULL
        ORDER BY id DESC;
      `;

      return rows.map(mapProductRow);
    } catch (error) {
      logFallback("products", error);
      return mockProducts;
    }
  },
  ["products"],
  { revalidate: REVALIDATE_SECONDS }
);

function mapProductRow(row: Record<string, unknown>): Product {
  return {
    id: Number(row.id),
    name: String(row.name),
    sku: (row.sku as string | null) ?? null,
    registeredDate: (row.registered_date as string | null) ?? null,
    productEnterCode: (row.product_enter_code as string | null) ?? null,
    cost: safeNumber(row.cost),
    price: safeNumber(row.price),
    pricingLocked: Number(row.pricing_locked || 0) === 1,
    stock: safeNumber(row.stock),
    frameColor: (row.frame_color as string | null) ?? null,
    lensColor: (row.lens_color as string | null) ?? null,
    style: (row.style as string | null) ?? null,
    palette: (row.palette as string | null) ?? null,
    gender: (row.gender as string | null) ?? null,
  };
}

// ---------- customers ----------

export const getCustomers = unstable_cache(
  async (tenantId = getTenantId()): Promise<Customer[]> => {
    if (!hasDatabaseUrl) return mockCustomers;

    try {
      const rows = await db()`
        SELECT id, customer_code, name, cpf, rg, phone, email, instagram,
               zip_code, street, number, neighborhood, city, state, country, created_at
        FROM customers
        WHERE tenant_id = ${tenantId}
        ORDER BY customer_code;
      `;

      return rows.map((row) => ({
        id: Number(row.id),
        customerCode: String(row.customer_code),
        name: String(row.name),
        cpf: (row.cpf as string | null) ?? null,
        rg: (row.rg as string | null) ?? null,
        phone: (row.phone as string | null) ?? null,
        email: (row.email as string | null) ?? null,
        instagram: (row.instagram as string | null) ?? null,
        zipCode: (row.zip_code as string | null) ?? null,
        street: (row.street as string | null) ?? null,
        number: (row.number as string | null) ?? null,
        neighborhood: (row.neighborhood as string | null) ?? null,
        city: (row.city as string | null) ?? null,
        state: (row.state as string | null) ?? null,
        country: (row.country as string | null) ?? null,
        createdAt: String(row.created_at),
      }));
    } catch (error) {
      logFallback("customers", error);
      return mockCustomers;
    }
  },
  ["customers"],
  { revalidate: REVALIDATE_SECONDS }
);

// ---------- inventory ----------

export const getInventory = unstable_cache(
  async (tenantId = getTenantId()): Promise<InventoryItem[]> => {
    if (!hasDatabaseUrl) {
      return mockProducts.map((product) => ({
        sku: product.sku || "SEM-SKU",
        totalStock: product.stock,
        avgUnitCost: product.cost,
        sellingPrice: product.price,
        sampleName: product.name,
      }));
    }

    try {
      const rows = await db()`
        SELECT sm.sku, sm.total_stock, sm.avg_unit_cost, sm.selling_price,
               (
                 SELECT p.name FROM products p
                 WHERE p.tenant_id = sm.tenant_id AND p.sku = sm.sku AND p.deleted_at IS NULL
                 ORDER BY p.id LIMIT 1
               ) AS sample_name
        FROM sku_master sm
        WHERE sm.tenant_id = ${tenantId}
          AND sm.deleted_at IS NULL
        ORDER BY sm.total_stock ASC, sm.sku ASC
        LIMIT 200;
      `;

      return rows.map((row) => ({
        sku: String(row.sku),
        totalStock: safeNumber(row.total_stock),
        avgUnitCost: safeNumber(row.avg_unit_cost),
        sellingPrice: safeNumber(row.selling_price),
        sampleName: (row.sample_name as string | null) ?? null,
      }));
    } catch (error) {
      logFallback("inventory", error);
      return mockProducts.map((product) => ({
        sku: product.sku || "SEM-SKU",
        totalStock: product.stock,
        avgUnitCost: product.cost,
        sellingPrice: product.price,
        sampleName: product.name,
      }));
    }
  },
  ["inventory"],
  { revalidate: REVALIDATE_SECONDS }
);

// ---------- sales ----------

export const getRecentSales = unstable_cache(
  async (tenantId = getTenantId()): Promise<Sale[]> => {
    if (!hasDatabaseUrl) return mockSales;

    try {
      const rows = await db()`
        SELECT id, sale_code, sku, quantity, total,
               COALESCE(total - COALESCE(cogs_total, 0), 0) AS profit,
               sold_at, payment_method, customer_id
        FROM sales
        WHERE tenant_id = ${tenantId}
        ORDER BY sold_at DESC, id DESC
        LIMIT 100;
      `;

      return rows.map((row) => ({
        id: Number(row.id),
        saleCode: (row.sale_code as string | null) ?? null,
        sku: (row.sku as string | null) ?? null,
        quantity: Number(row.quantity || 0),
        total: safeNumber(row.total),
        profit: safeNumber(row.profit),
        soldAt: String(row.sold_at),
        paymentMethod: (row.payment_method as string | null) ?? null,
        customerId: row.customer_id == null ? null : Number(row.customer_id),
      }));
    } catch (error) {
      logFallback("sales", error);
      return mockSales;
    }
  },
  ["recent-sales"],
  { revalidate: REVALIDATE_SECONDS }
);

export async function getSaleableSkus(tenantId = getTenantId()): Promise<SaleableSku[]> {
  if (!hasDatabaseUrl) {
    return mockProducts
      .filter((product) => product.stock > 0)
      .map((product) => ({
        sku: product.sku || "SEM-SKU",
        sellingPrice: product.price,
        totalStock: product.stock,
        sampleName: product.name,
      }));
  }

  try {
    const rows = await db()`
      SELECT sm.sku,
             COALESCE(sm.selling_price, 0) AS selling_price,
             COALESCE(sm.total_stock, 0) AS total_stock,
             (
               SELECT p.name FROM products p
               WHERE p.tenant_id = sm.tenant_id
                 AND p.sku = sm.sku AND p.deleted_at IS NULL
               ORDER BY p.id LIMIT 1
             ) AS sample_name
      FROM sku_master sm
      WHERE sm.tenant_id = ${tenantId}
        AND sm.deleted_at IS NULL
        AND COALESCE(sm.selling_price, 0) > 0
        AND COALESCE(sm.total_stock, 0) > 0
      ORDER BY sm.sku;
    `;

    return rows.map((row) => ({
      sku: String(row.sku),
      sellingPrice: safeNumber(row.selling_price),
      totalStock: safeNumber(row.total_stock),
      sampleName: (row.sample_name as string | null) ?? null,
    }));
  } catch (error) {
    logFallback("saleable skus", error);
    return [];
  }
}

export async function getBatchesForSku(
  sku: string,
  tenantId = getTenantId()
): Promise<ProductBatch[]> {
  if (!hasDatabaseUrl) {
    return mockProducts
      .filter((product) => product.sku === sku && product.stock > 0)
      .map((product) => ({
        id: product.id,
        name: product.name,
        stock: product.stock,
        productEnterCode: product.productEnterCode,
        frameColor: product.frameColor,
        lensColor: product.lensColor,
        style: product.style,
        palette: product.palette,
        gender: product.gender,
      }));
  }

  try {
    const rows = await db()`
      SELECT id, name, stock, product_enter_code,
             frame_color, lens_color, style, palette, gender
      FROM products
      WHERE tenant_id = ${tenantId}
        AND sku = ${sku}
        AND deleted_at IS NULL
        AND COALESCE(stock, 0) > 0
      ORDER BY id;
    `;

    return rows.map((row) => ({
      id: Number(row.id),
      name: String(row.name),
      stock: safeNumber(row.stock),
      productEnterCode: (row.product_enter_code as string | null) ?? null,
      frameColor: (row.frame_color as string | null) ?? null,
      lensColor: (row.lens_color as string | null) ?? null,
      style: (row.style as string | null) ?? null,
      palette: (row.palette as string | null) ?? null,
      gender: (row.gender as string | null) ?? null,
    }));
  } catch (error) {
    logFallback("batches for sku", error);
    return [];
  }
}

// ---------- costs + pricing ----------

export async function getSkuMasterRows(tenantId = getTenantId()): Promise<SkuMasterRow[]> {
  if (!hasDatabaseUrl) {
    return mockProducts.map((product) => ({
      sku: product.sku || "SEM-SKU",
      totalStock: product.stock,
      avgUnitCost: product.cost,
      sellingPrice: product.price,
      structuredCostTotal: product.cost * 0.85,
    }));
  }

  try {
    const rows = await db()`
      SELECT sku, total_stock, avg_unit_cost, selling_price, structured_cost_total
      FROM sku_master
      WHERE tenant_id = ${tenantId}
        AND deleted_at IS NULL
      ORDER BY sku;
    `;

    return rows.map((row) => ({
      sku: String(row.sku),
      totalStock: safeNumber(row.total_stock),
      avgUnitCost: safeNumber(row.avg_unit_cost),
      sellingPrice: safeNumber(row.selling_price),
      structuredCostTotal: safeNumber(row.structured_cost_total),
    }));
  } catch (error) {
    logFallback("sku master", error);
    return [];
  }
}

export async function getCostComponentsForSku(
  sku: string,
  tenantId = getTenantId()
): Promise<SkuCostComponent[]> {
  if (!hasDatabaseUrl) return [];

  try {
    const rows = await db()`
      SELECT component_key, COALESCE(unit_price, 0) AS unit_price,
             COALESCE(quantity, 0) AS quantity
      FROM sku_cost_components
      WHERE tenant_id = ${tenantId}
        AND sku = ${sku};
    `;
    return rows.map((row) => ({
      key: String(row.component_key),
      unitPrice: safeNumber(row.unit_price),
      unitQuantity: safeNumber(row.quantity),
    }));
  } catch (error) {
    logFallback("cost components", error);
    return [];
  }
}

export async function getActivePricingRecord(
  sku: string,
  tenantId = getTenantId()
): Promise<ActivePricingRecord | null> {
  if (!hasDatabaseUrl) return null;

  try {
    const rows = await db()`
      SELECT id, avg_cost_snapshot, markup_pct, taxes_pct, interest_pct,
             price_before_taxes, price_with_taxes, target_price,
             markup_kind, taxes_kind, interest_kind, is_active, created_at
      FROM sku_pricing_records
      WHERE tenant_id = ${tenantId}
        AND sku = ${sku}
        AND is_active = 1
      ORDER BY id DESC
      LIMIT 1;
    `;
    const row = rows[0];
    if (!row) return null;
    return {
      id: Number(row.id),
      avgCostSnapshot: safeNumber(row.avg_cost_snapshot),
      markupPct: safeNumber(row.markup_pct),
      taxesPct: safeNumber(row.taxes_pct),
      interestPct: safeNumber(row.interest_pct),
      priceBeforeTaxes: safeNumber(row.price_before_taxes),
      priceWithTaxes: safeNumber(row.price_with_taxes),
      targetPrice: safeNumber(row.target_price),
      markupKind: Number(row.markup_kind || 0),
      taxesKind: Number(row.taxes_kind || 0),
      interestKind: Number(row.interest_kind || 0),
      isActive: Number(row.is_active || 0) === 1,
      createdAt: String(row.created_at),
    };
  } catch (error) {
    logFallback("active pricing", error);
    return null;
  }
}

