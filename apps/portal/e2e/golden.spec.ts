// 로그인 → 대시보드 → admin 진입 → 화이트리스트 추가 → 로그아웃의 골든 패스.
import { test, expect } from "@playwright/test";
import { signInAsAdmin } from "./fixtures";

test("admin happy path", async ({ context, page }) => {
  const token = process.env.E2E_ADMIN_TOKEN;
  test.skip(!token, "Set E2E_ADMIN_TOKEN to run; see apps/portal/e2e/README.md");
  await signInAsAdmin(context, token!);
  await page.goto("/dashboard");
  await expect(page.getByText(/popory/i)).toBeVisible();
  await page.getByRole("link", { name: "어드민" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await page.getByRole("link", { name: "화이트리스트" }).click();
  await page.getByPlaceholder("email").fill("guest@example.com");
  await page.getByRole("button", { name: "추가" }).click();
  await expect(page.getByText("guest@example.com")).toBeVisible();
});
