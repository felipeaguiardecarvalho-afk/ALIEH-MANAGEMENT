import { test, expect } from "@playwright/test";

/**
 * Smoke E2E — protótipo oficial em http://127.0.0.1:3000
 * Pré-requisito: `npm run dev` na raiz (web-prototype) e API se a página exigir dados.
 */
test.describe("smoke", () => {
  test("home or login loads without crash", async ({ page }) => {
    const res = await page.goto("/", { waitUntil: "domcontentloaded", timeout: 30_000 });
    expect(res?.ok() || res?.status() === 307 || res?.status() === 302).toBeTruthy();
    await expect(page.locator("body")).toBeVisible();
  });

  test("login page reachable", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 30_000 });
    await expect(page.locator("body")).toBeVisible();
  });
});
