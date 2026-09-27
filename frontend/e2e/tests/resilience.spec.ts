import { test, expect } from '@playwright/test';

test.describe('Document Intelligence E2E - Resiliencia e Hidratación', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Login assuming admin exists
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'adminpassword');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Expedientes').first()).toBeVisible({ timeout: 10000 });
  });

  test('hidratación tras recarga', async ({ page }) => {
    // V6 Mocks
      await page.route('**/cases/999', async route => {
      await route.fulfill({ json: { id: 999, title: "Test Resilience", status: "EVALUATION", contract_type: "bienes", created_at: "2024-01-01" } });
    });

    await page.route('**/api/v6/cases/999/offers', async route => {
      await route.fulfill({ json: [
        { id: 101, supplier_id: 202, status: "APPROVED", price: 100, currency: "PEN", supplier: { business_name: "Proveedor Test" } }
      ] });
    });

    await page.route('**/api/v6/cases/999/evaluations/contractual', async route => {
      await route.fulfill({ json: [] });
    });

    await page.route('**/api/v6/cases/999/evaluations/vfm', async route => {
      await route.fulfill({ json: [] });
    });

    await page.route('**/api/v6/cases/999/evaluations', async route => {
      await route.fulfill({ json: [
        { id: 1, supplier_offer_id: 101, status: "PASSED", final_score: 100 }
      ] });
    });

    let postCount = 0;
    await page.route('**/api/v6/cases/999/offers/101/evaluate', async route => {
      if (route.request().method() === 'POST') {
        postCount++;
        await route.fulfill({ json: { status: "PASSED" } });
      } else {
        route.continue();
      }
    });

    await page.goto('/expedientes/999');
    await page.click('button:has-text("Evaluación")');

    // Confirm that the evaluation appears without evaluating
    await expect(page.locator('text=Re-evaluar Oferta')).toBeVisible({ timeout: 10000 });

    // Reload the page
    await page.reload();
    await page.click('button:has-text("Evaluación")');

    await expect(page.locator('text=Re-evaluar Oferta')).toBeVisible({ timeout: 10000 });

    // Validate that no POST requests were made
    expect(postCount).toBe(0);
  });

  test('reconciliación de estado uncertain', async ({ page }) => {
    await page.route('**/cases/888', async route => {
      await route.fulfill({ json: { id: 888, title: "Test Resilience 2", status: "EVALUATION", contract_type: "bienes", created_at: "2024-01-01" } });
    });

    await page.route('**/api/v6/cases/888/offers', async route => {
      await route.fulfill({ json: [
        { id: 102, supplier_id: 203, status: "APPROVED", price: 100, currency: "PEN", supplier: { business_name: "Proveedor Error" } }
      ] });
    });

    await page.route('**/api/v6/cases/888/evaluations/contractual', async route => { await route.fulfill({ json: [] }); });
    await page.route('**/api/v6/cases/888/evaluations/vfm', async route => { await route.fulfill({ json: [] }); });
    await page.route('**/api/v6/cases/888/evaluations', async route => { await route.fulfill({ json: [] }); });

    // Simulate a network failure on POST
    await page.route('**/api/v6/cases/888/offers/102/evaluate', async route => {
      if (route.request().method() === 'POST') {
        await route.abort('failed');
      } else {
        route.continue();
      }
    });

    await page.goto('/expedientes/888');
    await page.click('button:has-text("Evaluación")');

    // Click to evaluate
    await page.click('button:has-text("Evaluar Oferta")');

    // Should show error alert
    await expect(page.locator('text=Error de red al contactar al servidor')).toBeVisible({ timeout: 10000 });

    // The button should be re-enabled
    await expect(page.locator('button:has-text("Evaluar Oferta")')).toBeEnabled();
  });

  test('protección contra doble clic', async ({ page }) => {
    await page.route('**/cases/777', async route => {
      await route.fulfill({ json: { id: 777, title: "Test Resilience 3", status: "EVALUATION", contract_type: "bienes", created_at: "2024-01-01" } });
    });

    await page.route('**/api/v6/cases/777/offers', async route => {
      await route.fulfill({ json: [
        { id: 103, supplier_id: 204, status: "APPROVED", price: 100, currency: "PEN", supplier: { business_name: "Proveedor Lento" } }
      ] });
    });

    await page.route('**/api/v6/cases/777/evaluations/contractual', async route => { await route.fulfill({ json: [] }); });
    await page.route('**/api/v6/cases/777/evaluations/vfm', async route => { await route.fulfill({ json: [] }); });
    await page.route('**/api/v6/cases/777/evaluations', async route => { await route.fulfill({ json: [] }); });

    let postCount = 0;
    let finishRun: () => void = () => {};
    const runGate = new Promise<void>(resolve => { finishRun = resolve; });

    await page.route('**/api/v6/cases/777/offers/103/evaluate', async route => {
      if (route.request().method() === 'POST') {
        postCount++;
        await runGate;
        await route.fulfill({ json: { status: "PASSED" } });
      } else {
        route.continue();
      }
    });

    await page.goto('/expedientes/777');
    await page.click('button:has-text("Evaluación")');

    // Click twice rapidly
    const evaluateBtn = page.locator('button:has-text("Evaluar Oferta")');
    await evaluateBtn.click();
    await evaluateBtn.click({ force: true, timeout: 300 }).catch(() => {});

    // Verify it entered the running state while request is in flight
    await expect(page.locator('text=Evaluando...')).toBeVisible({ timeout: 5000 });

    // Release the network request
    finishRun();

    // After finishing, we should see Re-evaluar
    // We mock the evaluations GET to return the new evaluation so the UI updates
    await page.route('**/api/v6/cases/777/evaluations', async route => {
      await route.fulfill({ json: [{ id: 3, supplier_offer_id: 103, status: "PASSED" }] });
    });

    // The UI calls GET evaluations again after POST finishes, so it will hit the new mock
    await expect(page.locator('text=Re-evaluar Oferta')).toBeVisible({ timeout: 10000 });

    // Verify only 1 request was sent
    expect(postCount).toBe(1);
  });
});
