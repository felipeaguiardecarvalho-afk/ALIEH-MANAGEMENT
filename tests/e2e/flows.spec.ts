import { test, expect } from "@playwright/test";

const password = (process.env.ALIEH_E2E_PASSWORD || process.env.ALIEH_CI_E2E_PASSWORD || "").trim();
const username = (process.env.ALIEH_E2E_USERNAME || process.env.ALIEH_CI_E2E_USERNAME || "e2e_ci").trim();

test.describe.configure({ timeout: 120_000 });

test.beforeAll(() => {
  if (process.env.CI === "true" && !password) {
    throw new Error("CI requer ALIEH_E2E_PASSWORD ou ALIEH_CI_E2E_PASSWORD para fluxos E2E.");
  }
});

test("login — sessão e redirect para o painel", async ({ page }) => {
  test.skip(!password, "Defina ALIEH_E2E_PASSWORD (ou ALIEH_CI_E2E_PASSWORD) para este teste.");
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  const tenantSelect = page.locator('select[name="tenant_id"]');
  if (await tenantSelect.count()) {
    await tenantSelect.selectOption({ index: 0 });
  }
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 30_000 });
  expect(page.url()).toContain("/dashboard");
});

test("criar cliente — nome mínimo e confirmação", async ({ page }) => {
  test.skip(!password, "Defina ALIEH_E2E_PASSWORD para este teste.");
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  const tenantSelect = page.locator('select[name="tenant_id"]');
  if (await tenantSelect.count()) {
    await tenantSelect.selectOption({ index: 0 });
  }
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 30_000 });

  await page.goto("/customers/new", { waitUntil: "domcontentloaded" });
  await page.locator("#name").fill(`E2E Cliente ${Date.now()}`);
  await page.getByRole("button", { name: "Salvar cliente" }).click();
  await expect(page.getByText(/Cliente cadastrado/i)).toBeVisible({ timeout: 45_000 });
});

test("nova venda — página carrega após login", async ({ page }) => {
  test.skip(!password, "Defina ALIEH_E2E_PASSWORD para este teste.");
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  const tenantSelect = page.locator('select[name="tenant_id"]');
  if (await tenantSelect.count()) {
    await tenantSelect.selectOption({ index: 0 });
  }
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 30_000 });

  await page.goto("/sales/new", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /Nova venda/i })).toBeVisible({ timeout: 30_000 });
});

test("inventário — área autenticada acessível", async ({ page }) => {
  test.skip(!password, "Defina ALIEH_E2E_PASSWORD para este teste.");
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  const tenantSelect = page.locator('select[name="tenant_id"]');
  if (await tenantSelect.count()) {
    await tenantSelect.selectOption({ index: 0 });
  }
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 30_000 });

  await page.goto("/inventory", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /Cockpit de estoque/i })).toBeVisible({ timeout: 45_000 });
});

test.describe("UAT — cadeia curta", () => {
  test("painel → clientes → nova venda (smoke de navegação)", async ({ page }) => {
    test.skip(!password, "Defina ALIEH_E2E_PASSWORD para simulação UAT.");
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    const tenantSelect = page.locator('select[name="tenant_id"]');
    if (await tenantSelect.count()) {
      await tenantSelect.selectOption({ index: 0 });
    }
    await page.locator("#username").fill(username);
    await page.locator("#password").fill(password);
    await page.getByRole("button", { name: "Entrar" }).click();
    await page.waitForURL(/\/dashboard/, { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Painel executivo" })).toBeVisible({ timeout: 30_000 });
    await page.goto("/customers", { waitUntil: "domcontentloaded" });
    await expect(page.locator("main")).toBeVisible();
    await page.goto("/sales/new", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /Nova venda/i })).toBeVisible({ timeout: 20_000 });
  });
});
