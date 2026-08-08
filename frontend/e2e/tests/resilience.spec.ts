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
    await page.route('**/cases/999', async route => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      const json = { id: 999, title: "Test", status: "READY_GENERATE", contract_type: "Standard" };
      await route.fulfill({ json });
    });
    
    await page.route('**/cases/999/sections', async route => {
      await route.fulfill({ json: [] });
    });

    await page.route('**/cases/999/comparison', async route => {
      const json = [
        {
          id: 1,
          case_id: 999,
          field_name: "Plazo de Entrega",
          requirement_value: "30 días",
          quotation_value: "30 días",
          final_value: "30 días",
          status: "coincide"
        }
      ];
      await route.fulfill({ json });
    });

    // We track calls to POST comparison
    let postCount = 0;
    await page.route('**/cases/999/comparison/run', async route => {
      if (route.request().method() === 'POST') {
        postCount++;
        await route.fulfill({ json: { message: 'Comparison already completed', already_completed: true } });
      } else {
        route.continue();
      }
    });

    await page.goto('/cases/999');

    // Confirm that the results table appears and the button is enabled
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button:has-text("Generar Anexo Final")')).toBeEnabled();

    // Reload the page
    await page.reload();

    // The table should appear again without posting to comparison/run
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button:has-text("Generar Anexo Final")')).toBeEnabled();

    // Validate that no POST requests were made
    expect(postCount).toBe(0);
  });

  test('reconciliación de estado uncertain', async ({ page }) => {
    await page.route('**/cases/888', async route => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      const json = { id: 888, title: "Test", status: "COMPARING", contract_type: "Standard" };
      await route.fulfill({ json });
    });
    
    await page.route('**/cases/888/sections', async route => {
      await route.fulfill({ json: [] });
    });

    // Simulate a network failure on POST /comparison/run
    await page.route('**/cases/888/comparison/run', async route => {
      if (route.request().method() === 'POST') {
        await route.abort('failed'); // Simulating a network drop
      } else {
        route.continue();
      }
    });

    await page.goto('/cases/888');

    // Click to compare
    await page.click('button:has-text("Ejecutar Comparación")');

    // State should become uncertain. Check for error message or 'Verificar Estado'
    await expect(page.locator('button:has-text("Verificar Estado")')).toBeVisible({ timeout: 10000 });
    
    // Output generator should be blocked
    await expect(page.locator('button:has-text("Comparar Requerimiento vs Cotización")')).toBeDisabled();

    // Now mock the verification response
    await page.route('**/cases/888', async route => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      const json = { id: 888, title: "Test", status: "READY_GENERATE", contract_type: "Standard" };
      await route.fulfill({ json });
    });
    
    await page.route('**/cases/888/comparison', async route => {
      const json = [
        {
          id: 1,
          case_id: 888,
          field_name: "Garantía",
          requirement_value: "12 meses",
          quotation_value: "12 meses",
          final_value: "12 meses",
          status: "coincide"
        }
      ];
      await route.fulfill({ json });
    });

    await page.click('button:has-text("Verificar Estado")');

    // Table should appear
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button:has-text("Generar Anexo Final")')).toBeEnabled();
  });

  test('protección contra doble clic', async ({ page }) => {
    await page.route('**/cases/777', async route => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      const json = { id: 777, title: "Test", status: "COMPARING", contract_type: "Standard" };
      await route.fulfill({ json });
    });

    await page.route('**/cases/777/sections', async route => {
      await route.fulfill({ json: [] });
    });

    await page.route('**/cases/777/comparison', async route => {
      await route.fulfill({ json: [] });
    });

    let postCount = 0;
    let finishRun: () => void = () => {};
    const runGate = new Promise<void>(resolve => { finishRun = resolve; });

    await page.route('**/cases/777/comparison/run', async route => {
      if (route.request().method() === 'POST') {
        postCount++;
        await runGate;
        await route.fulfill({ json: { message: "success" } });
      } else {
        route.continue();
      }
    });

    await page.goto('/cases/777');

    // Click twice rapidly
    const compareBtn = page.locator('button:has-text("Ejecutar Comparación")');
    await compareBtn.click();
    await compareBtn.click({ force: true, timeout: 300 }).catch(() => {}); // force with short timeout in case it unmounts immediately

    // Verify it entered the running state while request is in flight
    await expect(page.locator('text=Comparando condiciones...')).toBeVisible({ timeout: 5000 });

    // Release the network request
    finishRun();

    // Verify only 1 request was sent
    expect(postCount).toBe(1);
  });
});
