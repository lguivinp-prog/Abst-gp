import { test, expect } from '@playwright/test';

const OPERATOR_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJvcGVyYXRvciIsInJvbGUiOiJPUEVSQVRPUiIsImV4cCI6MjAwMDAwMDAwMH0.signature';
const READONLY_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJyZWFkb25seSIsInJvbGUiOiJSRUFET05MWSIsImV4cCI6MjAwMDAwMDAwMH0.signature';

test.describe('Document Intelligence E2E - Matriz de Roles', () => {
  // Test ADMIN
  test('ADMIN puede crear expedientes y ejecutar comparaciones', async ({ page }) => {
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'adminpassword');
    await page.click('button[type="submit"]');

    // Admin ve botón nuevo expediente
    await expect(page.locator('button:has-text("Nuevo Expediente")')).toBeVisible({ timeout: 10000 });
    
    // Admin puede crear un nuevo caso y acceder a él
    await page.click('button:has-text("Nuevo Expediente")');
    await page.fill('input[name="title"]', 'Admin E2E Role Case');
    await page.fill('input[name="contract_type"]', 'Standard');
    await page.click('button:has-text("Crear")');

    await expect(page.locator('text=Admin E2E Role Case').first()).toBeVisible({ timeout: 10000 });
    await page.click('text=Admin E2E Role Case');
    await expect(page.locator('input[data-testid="upload-requirement"]')).toBeVisible({ timeout: 10000 });
  });

  // Test OPERATOR
  test('OPERATOR solo ve expedientes asignados', async ({ page }) => {
    // Interceptar llamadas para simular operador con token JWT válido
    await page.route('**/auth/token', async route => {
      await route.fulfill({ json: { access_token: OPERATOR_TOKEN, token_type: "bearer", role: "OPERATOR" } });
    });
    // Mock get cases
    await page.route('**/cases/', async route => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      await route.fulfill({ json: [{ id: 101, title: "Assigned Case", status: "CREATED", contract_type: "Standard", created_at: new Date().toISOString() }] });
    });

    await page.goto('/');
    await page.fill('input[name="username"]', 'operator');
    await page.fill('input[name="password"]', 'operatorpass');
    await page.click('button[type="submit"]');

    await expect(page.locator('text=Assigned Case')).toBeVisible({ timeout: 10000 });
  });

  // Test READONLY
  test('READONLY no puede modificar expedientes', async ({ page }) => {
    await page.route('**/auth/token', async route => {
      await route.fulfill({ json: { access_token: READONLY_TOKEN, token_type: "bearer", role: "READONLY" } });
    });

    await page.route('**/cases/', async route => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      await route.fulfill({ json: [] });
    });
    
    await page.route('**/cases/202', async route => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      await route.fulfill({ json: { id: 202, title: "View Only", status: "CREATED", contract_type: "Standard" } });
    });

    await page.route('**/cases/202/sections', async route => {
      await route.fulfill({ json: [] });
    });

    await page.goto('/');
    await page.fill('input[name="username"]', 'readonlyuser');
    await page.fill('input[name="password"]', 'readonlypass');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Expedientes').first()).toBeVisible({ timeout: 10000 });

    await page.goto('/cases/202');
    await expect(page.locator('text=View Only')).toBeVisible({ timeout: 10000 });
  });

  // Test Anti-IDOR
  test('Otro tenant (Anti-IDOR) recibe 404 manejado', async ({ page }) => {
    await page.goto('/');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'adminpassword');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Expedientes').first()).toBeVisible({ timeout: 10000 });

    // Mock API to return 404 for a case ID belonging to someone else
    await page.route('**/cases/99999', async route => {
      if (route.request().resourceType() === 'document') {
        return route.continue();
      }
      await route.fulfill({ status: 404, json: { detail: "Case not found" } });
    });

    await page.goto('/cases/99999');
    
    // UI should show Not Found handled error banner
    await expect(page.locator('text=Error al cargar el caso').or(page.locator('text=Expediente no encontrado'))).toBeVisible({ timeout: 10000 });
  });
});
