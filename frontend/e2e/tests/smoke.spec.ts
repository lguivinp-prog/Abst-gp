import { test, expect } from '@playwright/test';

test('Smoke login', async ({ page }) => {
  await page.goto('/');
  await page.fill('input[name="username"]', 'admin');
  await page.fill('input[name="password"]', 'adminpassword');
  await page.click('button[type="submit"]');

  await expect(page.locator('text=Expedientes').first()).toBeVisible({ timeout: 15000 });
});
