import { test, expect } from '@playwright/test';
import { Client } from 'pg';
import crypto from 'crypto';

const OPERATOR_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJvcGVyYXRvciIsInJvbGUiOiJPUEVSQVRPUiIsImV4cCI6MjA1MDAwMDAwMH0.mock_signature_operator';

test.describe('[UI-MOCK] Fase P12: Trazabilidad Documental y Verificación de Evidencia', () => {
  const mockCaseId = 401;
  const mockCase = {
    id: mockCaseId,
    title: 'Adquisición de Equipos Médicos P12',
    status: 'COMPARING',
    contract_type: 'bienes',
    created_at: new Date().toISOString()
  };

  const mockRequirements = [
    { id: 101, key: 'REQ-01', description: 'Garantía mínima de fábrica 24 meses', mandatory: true, status: 'VALIDATED', value: '24 meses' }
  ];

  const mockOffers = [
    {
      id: 201,
      case_id: mockCaseId,
      supplier_id: 11,
      status: 'APPROVED',
      price: 50000,
      total_amount: 50000,
      currency: 'PEN',
      supplier: { id: 11, ruc: '20555666777', business_name: 'Equipamiento Hospitalario SAC' },
      items: [{ id: 1, procurement_item_id: 1, unit_price: 50000, quantity: 1 }]
    }
  ];

  const mockEvaluations = [
    {
      id: 301,
      supplier_offer_id: 201,
      requirement_id: 101,
      status: 'REQUIERE_REVISION',
      explanation: 'Evidencia vinculada pendiente de verificacion humana suficiente',
      evaluation_confidence: 0.85
    }
  ];

  const mockEvidences = [
    {
      id: 501,
      case_id: mockCaseId,
      supplier_offer_id: 201,
      requirement_id: 101,
      offer_evidence_id: 1,
      source_document: 'ficha_tecnica_equipo.pdf',
      page: 12,
      fragment: 'Garantía extendida de fábrica: 36 meses con cobertura total de repuestos.',
      verification_status: 'PENDING',
      verified_by: null,
      verified_by_username: null,
      verified_at: null,
      notes: null
    }
  ];

  test('Acción Ver evidencia abre modal y muestra sustento verificable', async ({ page }) => {
    // Interceptar llamadas API
    await page.route('**/*', async (route) => {
      const url = route.request().url();

      if (route.request().resourceType() === 'document' || route.request().resourceType() === 'script' || route.request().resourceType() === 'stylesheet' || route.request().resourceType() === 'image') {
        return route.continue();
      }

      if (url.includes('/auth/token')) {
        return route.fulfill({ json: { access_token: OPERATOR_TOKEN, token_type: 'bearer', role: 'OPERATOR' } });
      }

      if (url.includes(`/cases/${mockCaseId}/sections`)) {
        return route.fulfill({ json: [] });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/evaluations/contractual`)) {
        return route.fulfill({ json: [] });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/evaluations/vfm`)) {
        return route.fulfill({ json: [] });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/evaluations`)) {
        return route.fulfill({ json: mockEvaluations });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/offers/201/requirements/101/evidence`)) {
        return route.fulfill({ json: mockEvidences });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/evidence/501/review`)) {
        const body = JSON.parse(route.request().postData() || '{}');
        const updated = {
          ...mockEvidences[0],
          verification_status: body.verification_status,
          verified_by: 1,
          verified_by_username: 'operador_responsable',
          verified_at: new Date().toISOString(),
          notes: body.notes
        };
        return route.fulfill({ json: updated });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/offers`)) {
        return route.fulfill({ json: mockOffers });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/requirements`)) {
        return route.fulfill({ json: mockRequirements });
      }

      if (url.includes(`/cases/${mockCaseId}`)) {
        return route.fulfill({ json: mockCase });
      }

      return route.fulfill({ json: {} });
    });

    await page.addInitScript((token) => {
      localStorage.setItem('access_token', token);
      localStorage.setItem('user', JSON.stringify({ id: 1, username: 'operador_responsable', role: 'OPERATOR' }));
    }, OPERATOR_TOKEN);

    // Navegar a la página de expediente del caso
    await page.goto(`/expedientes/${mockCaseId}`);

    // Cambiar a la pestaña de Evaluación
    await page.waitForSelector('button:has-text("Evaluación")', { timeout: 15000 });
    await page.click('button:has-text("Evaluación")');

    // Buscar y hacer click en botón Ver evidencia
    const verEvidenciaBtn = page.getByTestId('btn-ver-evidencia-201-101').or(page.getByTestId('btn-ver-evidencia-card-201-101')).first();
    await expect(verEvidenciaBtn).toBeVisible({ timeout: 10000 });
    await verEvidenciaBtn.click();

    // Comprobar que el modal de trazabilidad se abre
    await expect(page.getByText('Trazabilidad Documental y Evidencia Verificable')).toBeVisible();

    // Comprobar visualización de campos obligatorios
    await expect(page.getByText('ficha_tecnica_equipo.pdf')).toBeVisible();
    await expect(page.getByText('Página 12')).toBeVisible();
    await expect(page.getByText('Garantía extendida de fábrica: 36 meses con cobertura total de repuestos.')).toBeVisible();
    await expect(page.getByText('Pendiente de revisión').first()).toBeVisible();

    // Confirmar y validar evidencia
    const btnValidar = page.getByTestId('btn-validar-501');
    await expect(btnValidar).toBeVisible();
    await btnValidar.click();

    // Cerrar modal
    await page.getByRole('button', { name: 'Cerrar', exact: true }).click();
    await expect(page.getByText('Trazabilidad Documental y Evidencia Verificable')).not.toBeVisible();
  });
});

function parseHost(connStr: string): string {
  try {
    const url = new URL(connStr);
    return url.hostname;
  } catch {
    const match = connStr.match(/@([^:/]+)/);
    return match ? match[1] : '';
  }
}

async function verifyAuthorizedTestEnvironment(client: Client, connStr: string): Promise<void> {
  const host = parseHost(connStr);
  const authorizedHosts = ['db-test', 'localhost', '127.0.0.1'];
  if (!authorizedHosts.includes(host)) {
    throw new Error(`Conexión a host no autorizado rechazada: ${host}. Hosts autorizados: ${authorizedHosts.join(', ')}`);
  }

  const res = await client.query('SELECT current_database() AS db_name;');
  const dbName = res.rows[0]?.db_name;
  if (dbName !== 'test_db') {
    throw new Error(`Conexión a base no autorizada rechazada: ${dbName}. Solo se permite test_db.`);
  }
}

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

test.describe('[E2E-REAL-BACKEND] Integración Real de Trazabilidad sin Simulación', () => {
  let dbClient: Client;
  let testCaseId: number;
  let testDocId: number;
  let testOfferId: number;
  let testReqId: number;
  let testEvidenceLinkId: number;
  let supplierId: number;

  test.beforeAll(async () => {
    const connStr = process.env.DATABASE_URL || 'postgresql://test_user:test_password@db-test:5432/test_db';
    dbClient = new Client({ connectionString: connStr });
    await dbClient.connect();

    // Confirmar entorno autorizado antes de cualquier mutación SQL
    await verifyAuthorizedTestEnvironment(dbClient, connStr);

    // 1. Crear expediente real con régimen P12_STRICT
    const caseRes = await dbClient.query(`
      INSERT INTO case_files (title, status, contract_type, tenant_id, traceability_regime, created_at)
      VALUES ('Expediente Real P12 E2E', 'COMPARING', 'bienes', 'mega_tenant', 'P12_STRICT', NOW())
      RETURNING id;
    `);
    testCaseId = caseRes.rows[0].id;

    // 2. Crear documento subido real para el expediente (CORRECCIÓN 1)
    const docRes = await dbClient.query(`
      INSERT INTO uploaded_documents (case_id, document_type, original_filename, stored_path, mime_type, processing_status, created_at)
      VALUES ($1, 'quotation', 'ficha_tecnica_real.pdf', '/tmp/ficha_tecnica_real.pdf', 'application/pdf', 'completed', NOW())
      RETURNING id;
    `, [testCaseId]);
    testDocId = docRes.rows[0].id;

    // 3. Crear requisito real
    const reqRes = await dbClient.query(`
      INSERT INTO case_requirement_matrices (case_id, requirement_type, key, description, mandatory, status, created_at)
      VALUES ($1, 'TECHNICAL', 'REQ-E2E-P12', 'Garantía técnica de fábrica mínima 24 meses', true, 'VALIDATED', NOW())
      RETURNING id;
    `, [testCaseId]);
    testReqId = reqRes.rows[0].id;

    // 4. Crear proveedor sintético exclusivo para esta ejecución (sin búsqueda global por RUC)
    const synthRuc = '20999' + Date.now().toString().slice(-6);
    const synthName = `Proveedor Sintético P12 ${Date.now()}`;
    const supRes = await dbClient.query(`
      INSERT INTO suppliers (ruc, business_name, tenant_id, created_at)
      VALUES ($1, $2, 'mega_tenant', NOW())
      RETURNING id;
    `, [synthRuc, synthName]);
    supplierId = supRes.rows[0].id;

    await dbClient.query(`
      INSERT INTO supplier_profiles (supplier_id, validation_status)
      VALUES ($1, 'VERIFIED');
    `, [supplierId]);

    // 5. Crear oferta real
    const offRes = await dbClient.query(`
      INSERT INTO supplier_offers (case_id, supplier_id, status, evaluation_status, price, total_amount, currency, created_at)
      VALUES ($1, $2, 'APPROVED', 'PENDING', 75000, 75000, 'PEN', NOW())
      RETURNING id;
    `, [testCaseId, supplierId]);
    testOfferId = offRes.rows[0].id;

    // 6. Crear evidencia documental sintética asociada al documento real
    const evRes = await dbClient.query(`
      INSERT INTO offer_evidences (supplier_offer_id, document_id, document_type, fragment, confidence, page, created_at)
      VALUES ($1, $2, 'FICHA_TECNICA', 'Garantía extendida de fábrica 36 meses con repuestos genuinos.', 0.98, 5, NOW())
      RETURNING id;
    `, [testOfferId, testDocId]);
    const evidenceId = evRes.rows[0].id;

    // 7. Crear vinculación de trazabilidad P12 con estado PENDING y referencia a documento real
    const linkRes = await dbClient.query(`
      INSERT INTO offer_requirement_evidences (
        case_id, supplier_offer_id, requirement_id, offer_evidence_id, document_id,
        source_document, page, fragment, verification_status, notes, created_at, updated_at
      )
      VALUES ($1, $2, $3, $4, $5, 'ficha_tecnica_real.pdf', 5, 'Garantía extendida de fábrica 36 meses con repuestos genuinos.', 'PENDING', 'Pendiente de auditoría', NOW(), NOW())
      RETURNING id;
    `, [testCaseId, testOfferId, testReqId, evidenceId, testDocId]);
    testEvidenceLinkId = linkRes.rows[0].id;

    // 8. Insertar evaluación inicial REQUIERE_REVISION
    await dbClient.query(`
      INSERT INTO offer_evaluations (supplier_offer_id, requirement_id, status, explanation, evaluation_confidence, created_at)
      VALUES ($1, $2, 'REQUIERE_REVISION', 'Evidencia vinculada requiere revision humana', 0.98, NOW());
    `, [testOfferId, testReqId]);
  });

  test.afterAll(async () => {
    try {
      if (testCaseId) {
        await dbClient.query('DELETE FROM offer_requirement_evidences WHERE case_id = $1;', [testCaseId]);
        await dbClient.query('DELETE FROM offer_evaluations WHERE supplier_offer_id = $1;', [testOfferId]);
        await dbClient.query('DELETE FROM offer_evidences WHERE supplier_offer_id = $1;', [testOfferId]);
        await dbClient.query('DELETE FROM uploaded_documents WHERE case_id = $1;', [testCaseId]);
        await dbClient.query('DELETE FROM supplier_offers WHERE case_id = $1;', [testCaseId]);
        await dbClient.query('DELETE FROM case_requirement_matrices WHERE case_id = $1;', [testCaseId]);
        if (supplierId) {
          await dbClient.query('DELETE FROM supplier_profiles WHERE supplier_id = $1;', [supplierId]);
          await dbClient.query('DELETE FROM suppliers WHERE id = $1;', [supplierId]);
        }
        await dbClient.query('DELETE FROM case_files WHERE id = $1;', [testCaseId]);
      }
    } finally {
      await dbClient.end();
    }
  });

  test('Seguridad de entorno: intento de conexión a base no autorizada aborta sin mutaciones', async () => {
    const fakeConn = 'postgresql://test_user:test_password@unauthorized-prod-host:5432/production_db';
    const fakeClient = {
      query: async () => ({ rows: [{ db_name: 'production_db' }] })
    } as unknown as Client;

    // Ejecuta el guard real para verificar rechazo por host no autorizado
    await expect(verifyAuthorizedTestEnvironment(fakeClient, fakeConn)).rejects.toThrow(
      /Conexión a host no autorizado rechazada: unauthorized-prod-host/
    );

    // Ejecuta el guard real para verificar rechazo por base de datos no autorizada
    const badDbConn = 'postgresql://test_user:test_password@db-test:5432/unauthorized_db';
    await expect(verifyAuthorizedTestEnvironment(fakeClient, badDbConn)).rejects.toThrow(
      /Conexión a base no autorizada rechazada: production_db/
    );
  });

  test('Validación real de evidencia contra backend actualiza estado en base de datos sin simulación', async ({ page }) => {
    // 1. Inyectar token JWT real firmado para autenticación contra backend-app
    await page.addInitScript((token) => {
      window.localStorage.setItem('access_token', token);
    }, REAL_ADMIN_TOKEN);

    // 2. Navegar directamente al caso de prueba creado en PostgreSQL
    await page.goto(`/expedientes/${testCaseId}`);

    // 3. Ir a pestaña Evaluación
    await page.waitForSelector('button:has-text("Evaluación")', { timeout: 15000 });
    await page.click('button:has-text("Evaluación")');

    // 4. Abrir modal Ver evidencia
    const btnVerEvidencia = page.getByTestId(`btn-ver-evidencia-${testOfferId}-${testReqId}`)
      .or(page.getByTestId(`btn-ver-evidencia-card-${testOfferId}-${testReqId}`)).first();
    await expect(btnVerEvidencia).toBeVisible({ timeout: 15000 });
    await btnVerEvidencia.click();

    // 5. Comprobar datos reales provenientes de PostgreSQL
    await expect(page.getByText('Trazabilidad Documental y Evidencia Verificable')).toBeVisible();
    await expect(page.getByText('ficha_tecnica_real.pdf')).toBeVisible();
    await expect(page.getByText('Página 5')).toBeVisible();
    await expect(page.getByText('Garantía extendida de fábrica 36 meses con repuestos genuinos.')).toBeVisible();
    await expect(page.getByText('Pendiente de revisión').first()).toBeVisible();

    // 6. Ejecutar validación real (PUT /api/v6/cases/{case_id}/evidence/{evidence_link_id}/review)
    const btnValidar = page.getByTestId(`btn-validar-${testEvidenceLinkId}`);
    await expect(btnValidar).toBeVisible({ timeout: 10000 });
    await btnValidar.click();

    // 7. Esperar actualización de la UI a estado Verificado
    await expect(page.getByText('Verificada').first()).toBeVisible({ timeout: 10000 });

    // 8. Cerrar modal y verificar que el modal se cierra
    await page.getByRole('button', { name: 'Cerrar', exact: true }).click();
    await expect(page.getByText('Trazabilidad Documental y Evidencia Verificable')).not.toBeVisible();

    // 9. Comprobar persistencia real en PostgreSQL
    const checkDb = await dbClient.query(`
      SELECT verification_status, verified_by
      FROM offer_requirement_evidences
      WHERE id = $1;
    `, [testEvidenceLinkId]);
    expect(checkDb.rows[0]?.verification_status).toBe('VERIFIED');
    expect(checkDb.rows[0]?.verified_by).not.toBeNull();
  });
});

