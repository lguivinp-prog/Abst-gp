import { test, expect } from '@playwright/test';
import crypto from 'crypto';

// Tokens con expiración en el año 2035 (timestamp 2050000000)
// Base64 header: {"alg":"HS256","typ":"JWT"} -> eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
// Operator payload: {"sub":"operator","role":"OPERATOR","exp":2050000000} -> eyJzdWIiOiJvcGVyYXRvciIsInJvbGUiOiJPUEVSQVRPUiIsImV4cCI6MjA1MDAwMDAwMH0
// Supervisor payload: {"sub":"supervisor","role":"SUPERVISOR","exp":2050000000} -> eyJzdWIiOiJzdXBlcnZpc29yIiwicm9sZSI6IlNVUEVSVklTT1IiLCJleHAiOjIwNTAwMDAwMDB9
// Admin payload: {"sub":"admin","role":"ADMIN","exp":2050000000} -> eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJBRE1JTiIsImV4cCI6MjA1MDAwMDAwMH0
const OPERATOR_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJvcGVyYXRvciIsInJvbGUiOiJPUEVSQVRPUiIsImV4cCI6MjA1MDAwMDAwMH0.mock_signature_operator';
const SUPERVISOR_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdXBlcnZpc29yIiwicm9sZSI6IlNVUEVSVklTT1IiLCJleHAiOjIwNTAwMDAwMDB9.mock_signature_supervisor';

test.describe('[UI-MOCK] Fase P11: Matriz Comparativa, Selección Fundamentada y Aprobación Interna (API Simulada)', () => {

  const mockCaseId = 301;
  const mockCase = {
    id: mockCaseId,
    title: 'Adquisición de Laptops y Monitores P11',
    status: 'COMPARING',
    contract_type: 'bienes',
    created_at: new Date().toISOString()
  };

  const mockRequirements = [
    { id: 1, key: 'REQ-01', description: 'Memoria RAM mínima 32GB', mandatory: true, status: 'VALIDATED' },
    { id: 2, key: 'REQ-02', description: 'Garantía mínima 36 meses', mandatory: true, status: 'VALIDATED' }
  ];

  const mockOffers = [
    {
      id: 10,
      case_id: mockCaseId,
      supplier_id: 1,
      status: 'APPROVED',
      price: 25000,
      total_amount: 25000,
      currency: 'PEN',
      supplier: { id: 1, ruc: '20100000001', business_name: 'Soluciones Tecnológicas Alfa SAC' },
      items: [{ id: 1, procurement_item_id: 1, unit_price: 2500, quantity: 10 }]
    },
    {
      id: 20,
      case_id: mockCaseId,
      supplier_id: 2,
      status: 'APPROVED',
      price: 28000,
      total_amount: 28000,
      currency: 'PEN',
      supplier: { id: 2, ruc: '20200000002', business_name: 'Sistemas y Redes Beta SRL' },
      items: [{ id: 2, procurement_item_id: 1, unit_price: 2800, quantity: 10 }]
    }
  ];

  const mockConditions = [
    { id: 1, supplier_offer_id: 10, requirement_id: 1, status: 'CUMPLE', confidence: 0.95 },
    { id: 2, supplier_offer_id: 10, requirement_id: 2, status: 'CUMPLE_Y_MEJORA', confidence: 0.98 },
    { id: 3, supplier_offer_id: 20, requirement_id: 1, status: 'NO_CUMPLE', confidence: 0.92 },
    { id: 4, supplier_offer_id: 20, requirement_id: 2, status: 'REQUIERE_REVISION', confidence: 0.65 }
  ];

  const mockVFM = [
    { supplier_offer_id: 10, supplier_id: 1, is_eligible: true, is_evaluated: true, total_score: 15.0, price: 25000, vfm_ratio: 1666.67 },
    { supplier_offer_id: 20, supplier_id: 2, is_eligible: false, is_evaluated: true, total_score: 0.0, price: 28000, reason: 'FAILED_CONTRACTUAL_CONDITIONS' }
  ];

  // Helper para interceptar todas las peticiones de API y evitar 401s
  const setupApiMocks = async (page: any, customOverrides: { selection?: any; result?: any; caseStatus?: string } = {}) => {
    await page.route('**/*', async (route: any) => {
      const url = route.request().url();
      const method = route.request().method();

      // Permitir assets estáticos y html
      if (route.request().resourceType() === 'document' || route.request().resourceType() === 'script' || route.request().resourceType() === 'stylesheet' || route.request().resourceType() === 'image') {
        return route.continue();
      }

      if (url.includes('/auth/token')) {
        return route.fulfill({ json: { access_token: OPERATOR_TOKEN, token_type: 'bearer', role: 'OPERATOR' } });
      }

      if (url.includes(`/cases/${mockCaseId}/sections`)) {
        return route.fulfill({ json: [] });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/requirements`)) {
        return route.fulfill({ json: mockRequirements });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/offers`)) {
        return route.fulfill({ json: mockOffers });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/evaluations/contractual`)) {
        return route.fulfill({ json: mockConditions });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/evaluations/vfm`)) {
        return route.fulfill({ json: mockVFM });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/evaluations`)) {
        return route.fulfill({ json: mockConditions.map(c => ({ ...c, evaluation_confidence: c.confidence })) });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/selection`)) {
        if (method === 'GET') {
          return route.fulfill({ json: customOverrides.selection || null });
        }
        if (method === 'POST') {
          return route.fulfill({ json: { case_id: mockCaseId, status: 'UNDER_REVIEW' } });
        }
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/result`)) {
        return route.fulfill({ json: customOverrides.result || null });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/approve`)) {
        return route.fulfill({ json: { case_id: mockCaseId, status: 'APPROVED' } });
      }

      if (url.includes(`/cases/${mockCaseId}`)) {
        return route.fulfill({
          json: { ...mockCase, status: customOverrides.caseStatus || mockCase.status }
        });
      }

      if (url.includes('/cases/')) {
        return route.fulfill({ json: [mockCase] });
      }

      return route.continue();
    });
  };

  // ============================================================================
  // Test 1: Matriz visible con dos proveedores y correspondencia de requisitos
  // ============================================================================
  test('P11.1 & P11.2 & P11.3 & P11.4: Matriz comparativa multiproveedor y separación económica', async ({ page }) => {
    // Inyectar token en localStorage antes de que cargue la app
    await page.addInitScript((token) => {
      window.localStorage.setItem('access_token', token);
    }, OPERATOR_TOKEN);

    await setupApiMocks(page);

    await page.goto(`/expedientes/${mockCaseId}`);
    await expect(page.getByRole('heading', { name: 'Adquisición de Laptops y Monitores P11' })).toBeVisible({ timeout: 10000 });

    // Navegar a pestaña Evaluación
    await page.click('button:has-text("Evaluación")');

    // 1. Verificar matriz visible y encabezados de proveedores
    await expect(page.locator('text=Matriz Comparativa Multiproveedor')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Soluciones Tecnológicas Alfa SAC').first()).toBeVisible();
    await expect(page.locator('text=Sistemas y Redes Beta SRL').first()).toBeVisible();

    // 2. Verificar correspondencia de requisitos técnicos validados en filas
    await expect(page.locator('text=Memoria RAM mínima 32GB')).toBeVisible();
    await expect(page.locator('text=Garantía mínima 36 meses')).toBeVisible();

    // 3. Verificar estados de cumplimiento (badges)
    await expect(page.locator('text=Cumple').first()).toBeVisible();
    await expect(page.locator('text=No Cumple').first()).toBeVisible();
    await expect(page.locator('text=Revisión Necesaria').first()).toBeVisible();

    // 4. Separación visual entre precio y evaluación técnica
    await expect(page.locator('text=Oferta Económica (Términos Comerciales Visibles)')).toBeVisible();
    await expect(page.locator('text=Precio Total de la Oferta')).toBeVisible();
    await expect(page.locator('text=PEN 25,000.00').first()).toBeVisible();
    await expect(page.locator('text=PEN 28,000.00').first()).toBeVisible();
  });

  // ============================================================================
  // Test 2: Selección divergente bloqueada sin justificación y fundamentada aceptada
  // ============================================================================
  test('P11.5 & P11.6: Selección divergente bloqueada sin justificación y aceptada con fundamento', async ({ page }) => {
    let capturedProposal: any = null;

    await page.addInitScript((token) => {
      window.localStorage.setItem('access_token', token);
    }, OPERATOR_TOKEN);

    await setupApiMocks(page);

    // Interceptar llamada POST de selección para inspeccionar carga útil
    await page.route(`**/api/v6/cases/${mockCaseId}/selection`, async (route: any) => {
      if (route.request().method() === 'POST') {
        capturedProposal = JSON.parse(route.request().postData() || '{}');
        return route.fulfill({ json: { case_id: mockCaseId, status: 'UNDER_REVIEW' } });
      }
      return route.fulfill({ json: null });
    });

    await page.goto(`/expedientes/${mockCaseId}`);
    await expect(page.getByRole('heading', { name: 'Adquisición de Laptops y Monitores P11' })).toBeVisible({ timeout: 10000 });

    // Navegar a Selección
    await page.click('button:has-text("Selección")');

    await expect(page.locator('text=Propuesta de Selección Fundamentada')).toBeVisible({ timeout: 10000 });

    // Verificar insignias de recomendación
    await expect(page.locator('text=Recomendación Principal')).toBeVisible();
    await expect(page.locator('text=Propuesta Divergente')).toBeVisible();

    // Oferta Beta SRL (id 20) es divergente -> Botón debe estar deshabilitado inicialmente
    const betaBtn = page.getByRole('button', { name: 'Proponer Selección' }).last();
    await expect(betaBtn).toBeDisabled();

    // Ingresar justificación técnica obligatoria en el textarea de Beta SRL
    const textarea = page.locator('textarea').last();
    await textarea.fill('Se fundamenta selección por disponibilidad inmediata en almacén local y soporte 24/7.');

    // El botón debe quedar habilitado tras la justificación
    await expect(betaBtn).toBeEnabled();

    // Click en proponer selección
    await betaBtn.click();

    // Verificar que la API recibió la selección fundamentada con los contratos reales
    await expect.poll(() => capturedProposal).not.toBeNull();
    expect(capturedProposal.supplier_offer_id).toBe(20);
    expect(capturedProposal.justification_comment).toContain('Se fundamenta selección por disponibilidad');
  });

  // ============================================================================
  // Test 3: Gobernanza RBAC y Aprobación Interna sin adjudicación oficial
  // ============================================================================
  test('P11.7 & P11.8 & P11.9: RBAC aprobación interna exclusiva de supervisor y terminología correcta', async ({ page }) => {
    const mockSelection = {
      case_id: mockCaseId,
      status: 'UNDER_REVIEW',
      supplier_offer_id: 10,
      justification_comment: 'Selección conforme al ranking determinista.',
      selected_by: 1
    };

    const mockApprovedResult = {
      case_id: mockCaseId,
      attempt_id: 1,
      created_at: new Date().toISOString(),
      supplier_name: 'Soluciones Tecnológicas Alfa SAC',
      supplier_ruc: '20100000001',
      offer_total_amount: 25000,
      offer_currency: 'PEN',
      justification_comment: 'Selección conforme al ranking determinista.',
      status: 'APPROVED'
    };

    // --- Sub-test 1: OPERATOR accede a Resultado ---
    await page.addInitScript((token) => {
      window.localStorage.setItem('access_token', token);
    }, OPERATOR_TOKEN);

    await setupApiMocks(page, { selection: mockSelection, caseStatus: 'UNDER_REVIEW' });

    await page.goto(`/expedientes/${mockCaseId}`);
    await page.click('button:has-text("Resultado")');

    // Operador ve aviso informativo de sólo lectura
    await expect(page.locator('text=Propuesta de Selección Pendiente de Revisión')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Existe una propuesta de selección registrada en el expediente')).toBeVisible();
    await expect(page.locator('text=Acción de aprobación restringida: Solo usuarios con rol de Supervisor o Administrador')).toBeVisible();
    // Botón de aprobación NO debe renderizarse para el operador
    await expect(page.locator('button:has-text("Aprobar Propuesta de Selección")')).not.toBeVisible();

    // --- Sub-test 2: SUPERVISOR accede a Resultado ---
    const supContext = await page.context().browser()!.newContext();
    const supPage = await supContext.newPage();

    await supPage.addInitScript((token) => {
      window.localStorage.setItem('access_token', token);
    }, SUPERVISOR_TOKEN);

    let approveWasCalled = false;
    await setupApiMocks(supPage, { selection: mockSelection, caseStatus: 'UNDER_REVIEW' });
    await supPage.route(`**/api/v6/cases/${mockCaseId}/approve`, async (route: any) => {
      approveWasCalled = true;
      return route.fulfill({ json: { case_id: mockCaseId, status: 'APPROVED' } });
    });

    await supPage.goto(`/expedientes/${mockCaseId}`);
    await supPage.click('button:has-text("Resultado")');

    // Supervisor ve botón de aprobación con denominación institucional correcta
    const approveBtn = supPage.locator('button:has-text("Aprobar Propuesta de Selección")');
    await expect(approveBtn).toBeVisible({ timeout: 10000 });
    await approveBtn.click();
    await expect.poll(() => approveWasCalled).toBe(true);

    // --- Sub-test 3: Terminología y Disclaimer una vez Aprobado Internamente ---
    await setupApiMocks(supPage, { result: mockApprovedResult, caseStatus: 'COMPLETED' });
    await supPage.reload();
    await supPage.click('button:has-text("Resultado")');

    // Comprobar denominaciones aprobadas:
    await expect(supPage.locator('text=Selección Aprobada Internamente')).toBeVisible({ timeout: 10000 });
    await expect(supPage.locator('text=Proveedor Propuesto / Seleccionado')).toBeVisible();
    await expect(supPage.locator('text=Importe de la Oferta Seleccionada')).toBeVisible();
    await expect(supPage.locator('text=Aviso de alcance legal')).toBeVisible();

    // Asegurar que NO se utilicen expresiones de adjudicación vinculante oficial
    await expect(supPage.locator('text=Expediente Adjudicado')).not.toBeVisible();
    await expect(supPage.locator('text=Ganador Oficial')).not.toBeVisible();
    await expect(supPage.locator('text=Aprobar y Adjudicar')).not.toBeVisible();

    await supContext.close();
  });
});

// ============================================================================
// INTEGRADO-E2E: Recorrido Real contra Backend de Pruebas (sin mock de /approve)
// ============================================================================
test.describe('[INTEGRADO-E2E] Fase P11: Flujo Real de Aprobación contra Backend de Pruebas', () => {
  function makeRealTestJwt(username: string, role: string, secret: string = 'synthetic_secret_key_for_testing') {
    const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
    const now = Math.floor(Date.now() / 1000);
    const payload = Buffer.from(JSON.stringify({
      sub: username,
      role: role,
      iat: now,
      exp: now + 86400
    })).toString('base64url');
    const signature = crypto.createHmac('sha256', secret).update(`${header}.${payload}`).digest('base64url');
    return `${header}.${payload}.${signature}`;
  }

  const REAL_ADMIN_TOKEN = makeRealTestJwt('admin', 'ADMIN');

  test.beforeEach(async ({ request }) => {
    // Reset reproducible del expediente 901 a estado UNDER_REVIEW
    const res = await request.post('http://backend-app:8000/api/v6/cases/901/test-e2e-reset', {
      headers: {
        Authorization: `Bearer ${REAL_ADMIN_TOKEN}`
      }
    });
    expect([200, 204]).toContain(res.status());
  });

  test('[INTEGRADO-E2E] Aprobación interna real persistida contra backend-app sin interceptar /approve', async ({ page, request }) => {
    // 1. Inyectar token JWT real firmado para autenticación contra backend-app
    await page.addInitScript((token) => {
      window.localStorage.setItem('access_token', token);
    }, REAL_ADMIN_TOKEN);

    // 2. Navegar directamente al expediente real 901 sin simular rutas ni mockear la API
    await page.goto('/expedientes/901');
    await expect(page.getByRole('heading', { name: 'Expediente E2E Integrado P11' })).toBeVisible({ timeout: 15000 });

    // 3. Navegar a la pestaña Resultado
    await page.click('button:has-text("Resultado")');

    // 4. Verificar que la propuesta de selección registrada en UNDER_REVIEW se visualiza correctamente
    await expect(page.locator('text=Propuesta de Selección Pendiente de Revisión')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Oferta Propuesta: #901')).toBeVisible();

    // 5. El usuario con rol SUPERVISOR/ADMIN ve el botón institucional real de aprobación
    const approveBtn = page.locator('button:has-text("Aprobar Propuesta de Selección")');
    await expect(approveBtn).toBeVisible({ timeout: 10000 });

    // 6. Hacer clic en Aprobar SIN interceptar el endpoint /approve ni simular su respuesta
    await approveBtn.click();

    // 7. Verificar que la UI reacciona a la respuesta 200 real de backend-app y actualiza su estado
    await expect(page.locator('text=Selección Aprobada Internamente')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=Proveedor Propuesto / Seleccionado')).toBeVisible();
    await expect(page.locator('text=Tech Integration E2E SAC')).toBeVisible();
    await expect(page.locator('text=Importe de la Oferta Seleccionada')).toBeVisible();
    await expect(page.locator('text=Aviso de alcance legal')).toBeVisible();

    // 8. Verificar que la aprobación persiste realmente en el backend de pruebas
    const checkRes = await request.get('http://backend-app:8000/api/v6/cases/901/result', {
      headers: {
        Authorization: `Bearer ${REAL_ADMIN_TOKEN}`
      }
    });
    expect(checkRes.status()).toBe(200);
    const resultJson = await checkRes.json();
    expect(resultJson.status).toBe('APPROVED');
    expect(resultJson.supplier_name).toBe('Tech Integration E2E SAC');

    // 9. Comprobar que no existen expresiones de adjudicación vinculante oficial
    await expect(page.locator('text=Expediente Adjudicado')).not.toBeVisible();
    await expect(page.locator('text=Ganador Oficial')).not.toBeVisible();
    await expect(page.locator('text=Aprobar y Adjudicar')).not.toBeVisible();
  });
});

