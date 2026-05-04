export type DashboardKpis = {
  revenue: number;
  cost: number;
  profit: number;
  marginPct: number;
  salesCount: number;
  uniqueCustomers: number;
  ticketAvg: number;
  stockUnits: number;
};

export type Product = {
  id: number;
  name: string;
  sku: string | null;
  registeredDate: string | null;
  productEnterCode: string | null;
  cost: number;
  price: number;
  pricingLocked: boolean;
  stock: number;
  frameColor: string | null;
  lensColor: string | null;
  style: string | null;
  palette: string | null;
  gender: string | null;
};

export type Customer = {
  id: number;
  customerCode: string;
  name: string;
  cpf: string | null;
  rg: string | null;
  phone: string | null;
  email: string | null;
  instagram: string | null;
  zipCode: string | null;
  street: string | null;
  number: string | null;
  neighborhood: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  createdAt: string;
};

export type InventoryItem = {
  sku: string;
  totalStock: number;
  avgUnitCost: number;
  sellingPrice: number;
  sampleName: string | null;
};

export type Sale = {
  id: number;
  saleCode: string | null;
  sku: string | null;
  quantity: number;
  total: number;
  profit: number;
  soldAt: string;
  paymentMethod: string | null;
  customerId: number | null;
};

export type DailyRevenue = {
  day: string;
  revenue: number;
  profit: number;
};

export type SkuMasterRow = {
  sku: string;
  totalStock: number;
  avgUnitCost: number;
  sellingPrice: number;
  structuredCostTotal: number;
};

export type SkuCostComponent = {
  key: string;
  unitPrice: number;
  unitQuantity: number;
};

export type ActivePricingRecord = {
  id: number;
  avgCostSnapshot: number;
  markupPct: number;
  taxesPct: number;
  interestPct: number;
  priceBeforeTaxes: number;
  priceWithTaxes: number;
  targetPrice: number;
  markupKind: number;
  taxesKind: number;
  interestKind: number;
  isActive: boolean;
  createdAt: string;
};

export type SaleableSku = {
  sku: string;
  sellingPrice: number;
  totalStock: number;
  sampleName: string | null;
};

export type ProductBatch = {
  id: number;
  name: string;
  stock: number;
  productEnterCode: string | null;
  frameColor: string | null;
  lensColor: string | null;
  style: string | null;
  palette: string | null;
  gender: string | null;
};
