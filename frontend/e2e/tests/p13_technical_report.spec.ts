import { test, expect } from '@playwright/test';
import { Client } from 'pg';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import os from 'os';

function generateValidPeruvianRuc(): string {
  const prefix = '20';
  const middle = Math.floor(10000000 + Math.random() * 90000000).toString().slice(0, 8);
  const base = prefix + middle;
  const weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
  let sum = 0;
  for (let i = 0; i < 10; i++) {
    sum += parseInt(base[i], 10) * weights[i];
  }
  const mod = sum % 11;
  const checkDigit = (11 - mod) % 11;
  const finalDigit = checkDigit === 10 ? 0 : checkDigit;
  return base + finalDigit.toString();
}

const CANONICAL_P13_TEMPLATE_CONTENT = `<div class="technical-evaluation-report">
  <div class="report-header">
    <h1>INFORME TÉCNICO DE EVALUACIÓN Y SELECCIÓN INTERNA</h1>
    <p class="subtitle">Expediente: {{ case_code }} | Versión: {{ version_number }}</p>
  </div>
  <section class="report-section section-1">
    <h2>1. Expediente y Objeto de la Contratación</h2>
    {{ section_1_case_object_html }}
  </section>
  <section class="report-section section-2">
    <h2>2. Antecedentes Administrativos</h2>
    {{ section_2_antecedents_html }}
  </section>
  <section class="report-section section-3">
    <h2>3. Documentos Examinados y Hashes Sustentados</h2>
    {{ section_3_examined_documents_html }}
  </section>
  <section class="report-section section-4">
    <h2>4. Proveedores Participantes y Ofertas Presentadas</h2>
    {{ section_4_suppliers_offers_html }}
  </section>
  <section class="report-section section-5">
    <h2>5. Matriz de Evaluación Técnica y Cumplimiento de Requisitos</h2>
    {{ section_5_requirements_matrix_html }}
  </section>
  <section class="report-section section-6">
    <h2>6. Trazabilidad de Evidencias Acreditadas</h2>
    {{ section_6_evidence_traceability_html }}
  </section>
  <section class="report-section section-7">
    <h2>7. Resultados No Conformes y Revisión Humana</h2>
    {{ section_7_non_conformities_html }}
  </section>
  <section class="report-section section-8">
    <h2>8. Mejoras y Factores Diferenciadores Acreditados</h2>
    {{ section_8_improvements_html }}
  </section>
  <section class="report-section section-9">
    <h2>9. Condiciones Contractuales</h2>
    {{ section_9_contractual_conditions_html }}
  </section>
  <section class="report-section section-10">
    <h2>10. Evaluación Económica y Valor por Dinero (VfM)</h2>
    {{ section_10_economic_vfm_html }}
  </section>
  <section class="report-section section-11">
    <h2>11. Motivación y Cadena de Selección Interna</h2>
    {{ section_11_motivation_selection_html }}
  </section>
  <section class="report-section section-12">
    <h2>12. Conclusión, Alcance Legal, Firmas y Auditoría</h2>
    {{ section_12_conclusion_audit_html }}
  </section>
</div>`;

const OPERATOR_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJvcGVyYXRvciIsInJvbGUiOiJPUEVSQVRPUiIsImV4cCI6MjA1MDAwMDAwMH0.mock_signature_operator';
const SUPERVISOR_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdXBlcnZpc29yIiwicm9sZSI6IlNVUEVSVklTT1IiLCJleHAiOjIwNTAwMDAwMDB9.mock_signature_supervisor';

test.describe('[UI-MOCK: Component Interface Test] Fase P13: Informe Técnico (Pruebas de Componente con Mocks)', () => {
  const mockCaseId = 501;
  const mockCase = {
    id: mockCaseId,
    title: 'Adquisición de Equipos de Cómputo P13',
    status: 'APPROVED',
    contract_type: 'bienes',
    created_at: new Date().toISOString(),
  };

  const mockSelectionResult = {
    case_id: mockCaseId,
    supplier_offer_id: 301,
    supplier_name: 'Soluciones Tecnológicas del Perú S.A.C.',
    supplier_ruc: '20601234567',
    offer_currency: 'PEN',
    offer_total_amount: 45000.0,
    justification_comment: 'Mejor oferta técnica y económica con mayor puntuación VfM.',
    created_at: new Date().toISOString(),
    status: 'APPROVED',
  };

  let mockReports: any[] = [];

  test.beforeEach(() => {
    mockReports = [];
  });

  test('[UI-MOCK] Escenario 1: Interfaz de usuario - Generación, revisión formal, aprobación y modal de autenticidad', async ({ page }) => {
    mockReports = [
      {
        id: 1,
        case_id: String(mockCaseId),
        report_kind: 'INFORME_TECNICO_EVALUACION',
        version_number: 1,
        status: 'GENERATED',
        generated_by: 10,
        generated_at: new Date().toISOString(),
        approved_by: null,
        approved_at: null,
        rejected_by: null,
        rejected_at: null,
        snapshot_hash: 'a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0',
        html_hash: null,
        pdf_hash: null,
        has_pdf: false,
      },
    ];

    await page.route('**/*', async (route) => {
      const url = route.request().url();

      if (
        route.request().resourceType() === 'document' ||
        route.request().resourceType() === 'script' ||
        route.request().resourceType() === 'stylesheet' ||
        route.request().resourceType() === 'image'
      ) {
        return route.continue();
      }

      if (url.includes('/auth/token')) {
        return route.fulfill({
          json: { access_token: SUPERVISOR_TOKEN, token_type: 'bearer', role: 'SUPERVISOR' },
        });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/1/submit-review`) || url.includes('/reports/p13/reports/1/submit-review')) {
        mockReports[0].status = 'UNDER_REVIEW';
        return route.fulfill({ json: mockReports[0] });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/1/approve`) || url.includes('/reports/p13/reports/1/approve')) {
        mockReports[0].status = 'APPROVED';
        mockReports[0].approved_by = 20;
        mockReports[0].approved_at = new Date().toISOString();
        mockReports[0].approval_notes = 'Certificación técnica conforme';
        mockReports[0].html_hash = 'b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef01';
        mockReports[0].pdf_hash = 'c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef012';
        mockReports[0].has_pdf = true;
        return route.fulfill({ json: mockReports[0] });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/1/export/pdf`) || url.includes('/reports/p13/reports/1/export/pdf')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/pdf',
          body: Buffer.from('%PDF-1.4\n%ReportLab Generated\n%%EOF'),
        });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/1/integrity`) || url.includes('/reports/p13/reports/1/integrity')) {
        return route.fulfill({
          json: {
            report_id: 1,
            status: 'APPROVED',
            snapshot_intact: true,
            html_intact: true,
            pdf_intact: true,
            pdf_file_exists: true,
            is_authentic: true,
            details: 'Todos los dominios criptográficos coinciden byte a byte.',
          },
        });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/1`) || url.includes('/reports/p13/reports/1')) {
        return route.fulfill({ json: mockReports[0] });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13`) || url.includes(`/reports/p13/cases/${mockCaseId}/reports`)) {
        return route.fulfill({
          json: {
            case_id: String(mockCaseId),
            total: mockReports.length,
            reports: mockReports,
          },
        });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/result`)) {
        return route.fulfill({ json: mockSelectionResult });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/selection`)) {
        return route.fulfill({ json: mockSelectionResult });
      }

      if (url.includes(`/cases/${mockCaseId}`)) {
        return route.fulfill({ json: mockCase });
      }

      return route.fulfill({ json: {} });
    });

    await page.addInitScript((token) => {
      sessionStorage.setItem('access_token', token);
      sessionStorage.setItem('user', JSON.stringify({ id: 20, username: 'supervisor_demo', role: 'SUPERVISOR' }));
      localStorage.setItem('access_token', token);
      localStorage.setItem('user', JSON.stringify({ id: 20, username: 'supervisor_demo', role: 'SUPERVISOR' }));
    }, SUPERVISOR_TOKEN);

    await page.goto(`/expedientes/${mockCaseId}`);
    await page.waitForSelector('button:has-text("Resultado")', { timeout: 15000 });
    await page.click('button:has-text("Resultado")');

    // Panel de informe técnico debe estar visible
    await expect(page.locator('text=Informe Técnico de Evaluación y Selección (P13)')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button.tech-report-tab:has-text("Versión 1")')).toBeVisible();
    await expect(page.locator('.tech-report-card').getByText('Borrador (Generado)')).toBeVisible();

    // Enviar a revisión formal
    await page.click('button:has-text("Enviar a Revisión Formal")');
    await expect(page.locator('.tech-report-card').getByText('En Revisión Formal')).toBeVisible({ timeout: 10000 });

    // Aprobar informe con notas
    await page.click('button:has-text("Aprobar Informe")');
    await expect(page.locator('text=Aprobar Informe Técnico (v1)')).toBeVisible();
    await page.fill('textarea[placeholder*="Ejemplo: Se certifica"]', 'Aprobado sin observaciones.');
    await page.click('button:has-text("Confirmar Aprobación")');

    // Verificar estado Aprobado y Certificado
    await expect(page.locator('.tech-report-card').getByText('Aprobado y Certificado')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button:has-text("Descargar PDF Certificado")')).toBeVisible();

    // Verificar autenticidad criptográfica
    await page.click('button:has-text("Verificar Autenticidad")');
    await expect(page.locator('text=Certificación Criptográfica de Autenticidad')).toBeVisible();
    await expect(page.locator('text=Autenticidad Criptográfica Verificada')).toBeVisible();
    await page.locator('.tech-report-modal button:has-text("Cerrar")').click();
  });

  test('[UI-MOCK] Escenario 2: Interfaz de usuario - Validación visual de SoD en panel para autor operador', async ({ page }) => {
    mockReports = [
      {
        id: 1,
        case_id: String(mockCaseId),
        report_kind: 'INFORME_TECNICO_EVALUACION',
        version_number: 1,
        status: 'UNDER_REVIEW',
        generated_by: 10,
        generated_at: new Date().toISOString(),
        approved_by: null,
        approved_at: null,
        rejected_by: null,
        rejected_at: null,
        snapshot_hash: 'a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0',
        html_hash: null,
        pdf_hash: null,
        has_pdf: false,
      },
    ];

    await page.route('**/*', async (route) => {
      const url = route.request().url();

      if (
        route.request().resourceType() === 'document' ||
        route.request().resourceType() === 'script' ||
        route.request().resourceType() === 'stylesheet' ||
        route.request().resourceType() === 'image'
      ) {
        return route.continue();
      }

      if (url.includes('/auth/token')) {
        return route.fulfill({
          json: { access_token: OPERATOR_TOKEN, token_type: 'bearer', role: 'OPERATOR' },
        });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/1`) || url.includes('/reports/p13/reports/1')) {
        return route.fulfill({ json: mockReports[0] });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13`) || url.includes(`/reports/p13/cases/${mockCaseId}/reports`)) {
        return route.fulfill({
          json: {
            case_id: String(mockCaseId),
            total: 1,
            reports: mockReports,
          },
        });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/result`)) {
        return route.fulfill({ json: mockSelectionResult });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/selection`)) {
        return route.fulfill({ json: mockSelectionResult });
      }

      if (url.includes(`/cases/${mockCaseId}`)) {
        return route.fulfill({ json: mockCase });
      }

      return route.fulfill({ json: {} });
    });

    await page.addInitScript((token) => {
      sessionStorage.setItem('access_token', token);
      sessionStorage.setItem('user', JSON.stringify({ id: 10, username: 'autor_operador', role: 'OPERATOR' }));
      localStorage.setItem('access_token', token);
      localStorage.setItem('user', JSON.stringify({ id: 10, username: 'autor_operador', role: 'OPERATOR' }));
    }, OPERATOR_TOKEN);

    await page.goto(`/expedientes/${mockCaseId}`);
    await page.waitForSelector('button:has-text("Resultado")', { timeout: 15000 });
    await page.click('button:has-text("Resultado")');

    // Verificar que informe está en revisión
    await expect(page.locator('.tech-report-card').getByText('En Revisión Formal')).toBeVisible({ timeout: 10000 });

    // El usuario operador autor no tiene botones de aprobación directa habilitados
    await expect(page.locator('button:has-text("Aprobar Informe")')).not.toBeVisible();
  });

  test('[UI-MOCK] Escenario 3: Interfaz de usuario - Visualización de rechazo con observaciones y control de versiones', async ({ page }) => {
    mockReports = [
      {
        id: 1,
        case_id: String(mockCaseId),
        report_kind: 'INFORME_TECNICO_EVALUACION',
        version_number: 1,
        status: 'UNDER_REVIEW',
        generated_by: 10,
        generated_at: new Date().toISOString(),
        approved_by: null,
        approved_at: null,
        rejected_by: null,
        rejected_at: null,
        snapshot_hash: 'a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0',
        html_hash: null,
        pdf_hash: null,
        has_pdf: false,
      },
    ];

    await page.route('**/*', async (route) => {
      const url = route.request().url();

      if (
        route.request().resourceType() === 'document' ||
        route.request().resourceType() === 'script' ||
        route.request().resourceType() === 'stylesheet' ||
        route.request().resourceType() === 'image'
      ) {
        return route.continue();
      }

      if (url.includes('/auth/token')) {
        return route.fulfill({
          json: { access_token: SUPERVISOR_TOKEN, token_type: 'bearer', role: 'SUPERVISOR' },
        });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/1/reject`) || url.includes('/reports/p13/reports/1/reject')) {
        const body = JSON.parse(route.request().postData() || '{}');
        mockReports[0].status = 'REJECTED';
        mockReports[0].rejected_by = 20;
        mockReports[0].rejected_at = new Date().toISOString();
        mockReports[0].rejection_reason = body.rejection_reason || 'Observación técnica en requisitos.';
        return route.fulfill({ json: mockReports[0] });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/generate`) || url.includes(`/reports/p13/cases/${mockCaseId}/generate`)) {
        const newReport = {
          id: 2,
          case_id: String(mockCaseId),
          report_kind: 'INFORME_TECNICO_EVALUACION',
          version_number: 2,
          status: 'GENERATED',
          generated_by: 10,
          generated_at: new Date().toISOString(),
          approved_by: null,
          approved_at: null,
          rejected_by: null,
          rejected_at: null,
          snapshot_hash: 'd4e5f67890123456789abcdef0123456789abcdef0123456789abcdef01234567',
          html_hash: null,
          pdf_hash: null,
          has_pdf: false,
        };
        mockReports.unshift(newReport);
        return route.fulfill({ json: newReport });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/2`) || url.includes('/reports/p13/reports/2')) {
        return route.fulfill({ json: mockReports[0] });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13/1`) || url.includes('/reports/p13/reports/1')) {
        return route.fulfill({ json: mockReports[mockReports.length - 1] });
      }

      if (url.includes(`/cases/${mockCaseId}/reports/p13`) || url.includes(`/reports/p13/cases/${mockCaseId}/reports`)) {
        return route.fulfill({
          json: {
            case_id: String(mockCaseId),
            total: mockReports.length,
            reports: mockReports,
          },
        });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/result`)) {
        return route.fulfill({ json: mockSelectionResult });
      }

      if (url.includes(`/api/v6/cases/${mockCaseId}/selection`)) {
        return route.fulfill({ json: mockSelectionResult });
      }

      if (url.includes(`/cases/${mockCaseId}`)) {
        return route.fulfill({ json: mockCase });
      }

      return route.fulfill({ json: {} });
    });

    await page.addInitScript((token) => {
      sessionStorage.setItem('access_token', token);
      sessionStorage.setItem('user', JSON.stringify({ id: 20, username: 'supervisor_demo', role: 'SUPERVISOR' }));
      localStorage.setItem('access_token', token);
      localStorage.setItem('user', JSON.stringify({ id: 20, username: 'supervisor_demo', role: 'SUPERVISOR' }));
    }, SUPERVISOR_TOKEN);

    await page.goto(`/expedientes/${mockCaseId}`);
    await page.waitForSelector('button:has-text("Resultado")', { timeout: 15000 });
    await page.click('button:has-text("Resultado")');

    // Rechazar con observaciones
    await page.click('button:has-text("Rechazar con Observaciones")');
    await expect(page.locator('text=Rechazar Informe Técnico (v1)')).toBeVisible();
    await page.fill('textarea[placeholder*="Detalle de observaciones"]', 'Falta subsanar sustento del requerimiento 3.');
    await page.click('button:has-text("Confirmar Rechazo")');

    // Verificar estado REJECTED y motivo visible
    await expect(page.locator('.tech-report-card').getByText('Rechazado con Observaciones')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Falta subsanar sustento del requerimiento 3.')).toBeVisible();

    // Generar nueva versión v2
    await page.click('button:has-text("Generar Nuevo Informe (v2)")');
    await expect(page.locator('button.tech-report-tab:has-text("Versión 2")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.tech-report-card').getByText('Borrador (Generado)')).toBeVisible();
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

async function assertSafeDatabaseSession(client: Client, connStr: string): Promise<void> {
  const host = parseHost(connStr);
  const authorizedHosts = ['db-test', 'localhost', '127.0.0.1'];
  if (!authorizedHosts.includes(host)) {
    throw new Error(`Conexión a host no autorizado rechazada: ${host}. Hosts autorizados: ${authorizedHosts.join(', ')}`);
  }

  const res = await client.query('SELECT current_database() AS db_name, current_user AS user_name;');
  const dbName = res.rows[0]?.db_name;
  const userName = res.rows[0]?.user_name;
  if (dbName !== 'test_db') {
    throw new Error(`Conexión a base no autorizada rechazada: ${dbName}. Solo se permite test_db.`);
  }
  if (userName !== 'test_user') {
    throw new Error(`Conexión con usuario no autorizado rechazada: ${userName}. Solo se permite test_user.`);
  }
}

function makeRealTestJwt(username: string, role: string, jti: string, secret: string = 'synthetic_secret_key_for_testing') {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const now = Math.floor(Date.now() / 1000);
  const payload = Buffer.from(JSON.stringify({
    sub: username,
    role: role,
    jti: jti,
    session_version: 1,
    purpose: 'access',
    tenant_id: 'mega_tenant',
    iat: now,
    exp: now + 86400,
  })).toString('base64url');
  const signature = crypto.createHmac('sha256', secret).update(`${header}.${payload}`).digest('base64url');
  return `${header}.${payload}.${signature}`;
}

test.describe('[E2E-REAL-BACKEND] Integración Real de Informe Técnico P13 sin Mocks', () => {
  let dbClient: Client;
  let testCaseId: number;
  let browserCaseId: number;
  let testDocId: number;
  let browserDocId: number;
  let testOfferId: number;
  let browserOfferId: number;
  let testReqId: number;
  let browserReqId: number;
  let testEvidenceId: number;
  let browserEvidenceId: number;
  let testEvidenceLinkId: number;
  let browserEvidenceLinkId: number;
  let supplierId: number;
  let operatorUserId: number;
  let supervisorUserId: number;
  let preexistingUserId: number;
  let realDocDiskPath: string;
  let templateBackup: { id: number; content: string; checksum: string; status: string } | null = null;

  const RUN_TAG = `${Date.now()}_${Math.floor(Math.random() * 10000)}`;
  const PREEXISTING_USER = `p13_pre_${RUN_TAG}`;
  const OPERATOR_USER = `p13_op_${RUN_TAG}`;
  const SUPERVISOR_USER = `p13_sup_${RUN_TAG}`;
  const OP_JTI = `test-jti-p13-op-${RUN_TAG}`;
  const SUP_JTI = `test-jti-p13-sup-${RUN_TAG}`;
  const REAL_OP_JWT = makeRealTestJwt(OPERATOR_USER, 'OPERATOR', OP_JTI);
  const REAL_SUP_JWT = makeRealTestJwt(SUPERVISOR_USER, 'SUPERVISOR', SUP_JTI);

  const API_BASE = process.env.API_URL || 'http://backend-app:8000';

  test.beforeAll(async () => {
    const connStr = process.env.DATABASE_URL || 'postgresql://test_user:test_password@db-test:5432/test_db';
    dbClient = new Client({ connectionString: connStr });
    await dbClient.connect();

    // Verificación estricta de entorno de test autorizado [R2-07]
    await assertSafeDatabaseSession(dbClient, connStr);

    // 0. Crear usuario preexistente independiente para prueba adversaria de no-mutación [Sección III]
    const preRes = await dbClient.query(`
      INSERT INTO users (username, role, tenant_id, password_hash, tenant_resolution_status, is_active, must_change_password, failed_login_count, created_at)
      VALUES ($1, 'OPERATOR', 'mega_tenant', 'mock_hash', 'RESOLVED', true, false, 0, NOW())
      RETURNING id;
    `, [PREEXISTING_USER]);
    preexistingUserId = preRes.rows[0].id;

    // 1. Respaldo preventivo de plantilla global antes de cualquier modificación [R2-07]
    const tCheck = await dbClient.query(`
      SELECT id, content, checksum, status FROM output_templates
      WHERE type = 'INFORME_TECNICO_EVALUACION' AND version = '1.0' AND entity_name = 'Abast-gp';
    `);
    if (tCheck.rows.length > 0) {
      templateBackup = tCheck.rows[0];
    }

    // 2. Ensure Tenant mega_tenant
    await dbClient.query(`
      INSERT INTO tenants (id, name, created_at)
      VALUES ('mega_tenant', 'Mega Tenant', NOW())
      ON CONFLICT (id) DO NOTHING;
    `);

    // 3. Crear usuarios aislados con nombres únicos sin ON CONFLICT DO UPDATE [R3-05]
    const opUserRes = await dbClient.query(`
      INSERT INTO users (username, role, tenant_id, password_hash, tenant_resolution_status, is_active, must_change_password, failed_login_count, created_at)
      VALUES ($1, 'OPERATOR', 'mega_tenant', 'mock_hash', 'RESOLVED', true, false, 0, NOW())
      RETURNING id;
    `, [OPERATOR_USER]);
    operatorUserId = opUserRes.rows[0].id;

    const supUserRes = await dbClient.query(`
      INSERT INTO users (username, role, tenant_id, password_hash, tenant_resolution_status, is_active, must_change_password, failed_login_count, created_at)
      VALUES ($1, 'SUPERVISOR', 'mega_tenant', 'mock_hash', 'RESOLVED', true, false, 0, NOW())
      RETURNING id;
    `, [SUPERVISOR_USER]);
    supervisorUserId = supUserRes.rows[0].id;

    await dbClient.query(`
      INSERT INTO user_sessions (id, user_id, session_version, created_at, expires_at, is_revoked)
      VALUES ($1, $2, 1, NOW(), NOW() + interval '1 day', false)
      ON CONFLICT (id) DO NOTHING;
    `, [OP_JTI, operatorUserId]);

    await dbClient.query(`
      INSERT INTO user_sessions (id, user_id, session_version, created_at, expires_at, is_revoked)
      VALUES ($1, $2, 1, NOW(), NOW() + interval '1 day', false)
      ON CONFLICT (id) DO NOTHING;
    `, [SUP_JTI, supervisorUserId]);

    // 4. Asegurar plantilla canónica oficial P13 de 12 secciones [R3-07]
    const canonicalChecksum = crypto.createHash('sha256').update(CANONICAL_P13_TEMPLATE_CONTENT, 'utf8').digest('hex');
    if (!templateBackup) {
      await dbClient.query(`
        INSERT INTO output_templates (type, version, entity_name, content, checksum, status, created_at)
        VALUES ('INFORME_TECNICO_EVALUACION', '1.0', 'Abast-gp', $1, $2, 'ACTIVE', NOW());
      `, [CANONICAL_P13_TEMPLATE_CONTENT, canonicalChecksum]);
    } else {
      await dbClient.query(`
        UPDATE output_templates SET content = $1, checksum = $2, status = 'ACTIVE'
        WHERE id = $3;
      `, [CANONICAL_P13_TEMPLATE_CONTENT, canonicalChecksum, templateBackup.id]);
    }

    // 5. Crear documento físico real en almacenamiento para R3-04
    const uploadsDir = fs.existsSync('/app/uploads') ? '/app/uploads' : (process.env.TEMP || os.tmpdir());
    realDocDiskPath = path.join(uploadsDir, `especificaciones_p13_${RUN_TAG}.pdf`);
    const authenticPdfBytes = Buffer.from(
      '%PDF-1.4\n%Authentic P13 Test Specifications Document\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000018 00000 n \n0000000077 00000 n \n0000000133 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n214\n%%EOF\n'
    );
    fs.writeFileSync(realDocDiskPath, authenticPdfBytes);

    // 6. Crear Proveedor con RUC peruano válido SUNAT Módulo 11 [R3-10]
    const validRuc = generateValidPeruvianRuc();
    const supRes = await dbClient.query(`
      INSERT INTO suppliers (ruc, business_name, tenant_id, created_at)
      VALUES ($1, 'Proveedor Tecnico Real P13 SAC', 'mega_tenant', NOW())
      RETURNING id;
    `, [validRuc]);
    supplierId = supRes.rows[0].id;

    await dbClient.query(`
      INSERT INTO supplier_profiles (supplier_id, validation_status)
      VALUES ($1, 'VERIFIED')
      ON CONFLICT (supplier_id) DO UPDATE SET validation_status = 'VERIFIED';
    `, [supplierId]);

    // Función auxiliar para sembrar un expediente completo
    async function seedCase(title: string, suffix: string) {
      const caseRes = await dbClient.query(`
        INSERT INTO case_files (title, status, contract_type, tenant_id, assigned_to_user_id, traceability_regime, siga_number, created_at)
        VALUES ($1, 'APPROVED', 'BIENES', 'mega_tenant', $2, 'P12_STRICT', $3, NOW())
        RETURNING id;
      `, [title, operatorUserId, `EXP-P13-${suffix}`]);
      const cId = caseRes.rows[0].id;

      await dbClient.query(`
        INSERT INTO case_workflows (case_id, status, supervisor_id, created_at)
        VALUES ($1, 'APPROVED', $2, NOW())
        ON CONFLICT (case_id) DO UPDATE SET status = 'APPROVED', supervisor_id = $2;
      `, [cId, supervisorUserId]);

      const offerRes = await dbClient.query(`
        INSERT INTO supplier_offers (case_id, supplier_id, status, evaluation_status, price, total_amount, currency, created_at)
        VALUES ($1, $2, 'SELECTED', 'SELECTED', 35000.00, 35000.00, 'PEN', NOW())
        RETURNING id;
      `, [cId, supplierId]);
      const oId = offerRes.rows[0].id;

      const attemptRes = await dbClient.query(`
        INSERT INTO supplier_selection_attempts (case_id, supplier_offer_id, selected_by, status, created_at)
        VALUES ($1, $2, $3, 'UNDER_REVIEW', NOW())
        RETURNING id;
      `, [cId, oId, operatorUserId]);
      const aId = attemptRes.rows[0].id;

      await dbClient.query(`
        INSERT INTO supplier_selection_final (case_id, attempt_id, created_at)
        VALUES ($1, $2, NOW());
      `, [cId, aId]);

      const docRes = await dbClient.query(`
        INSERT INTO uploaded_documents (case_id, document_type, original_filename, stored_path, mime_type, processing_status, created_at)
        VALUES ($1, 'requirement', $2, $3, 'application/pdf', 'completed', NOW())
        RETURNING id;
      `, [cId, `especificaciones_p13_${suffix}.pdf`, realDocDiskPath]);
      const dId = docRes.rows[0].id;

      const reqRes = await dbClient.query(`
        INSERT INTO case_requirement_matrices (case_id, requirement_type, key, description, mandatory, status, created_at)
        VALUES ($1, 'TECHNICAL', 'REQ-P13-MANDATORY', 'Garantía técnica mínima de 24 meses', true, 'VALIDATED', NOW())
        RETURNING id;
      `, [cId]);
      const rId = reqRes.rows[0].id;

      await dbClient.query(`
        INSERT INTO offer_evaluations (supplier_offer_id, requirement_id, status, explanation, evaluation_confidence, validated_by, created_at)
        VALUES ($1, $2, 'PASSED', 'Requisito técnico acreditado', 0.99, $3, NOW());
      `, [oId, rId, operatorUserId]);

      const evRes = await dbClient.query(`
        INSERT INTO offer_evidences (supplier_offer_id, document_id, document_type, fragment, confidence, page, created_at)
        VALUES ($1, $2, 'FICHA_TECNICA', 'Cumple con garantía extendida de fábrica 24 meses.', 0.99, 1, NOW())
        RETURNING id;
      `, [oId, dId]);
      const eId = evRes.rows[0].id;

      const linkRes = await dbClient.query(`
        INSERT INTO offer_requirement_evidences (
          case_id, supplier_offer_id, requirement_id, offer_evidence_id, document_id,
          source_document, page, fragment, verification_status, verified_by, notes, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, 1, 'Cumple con garantía extendida de fábrica 24 meses.', 'VERIFIED', $7, 'Auditado conforme', NOW(), NOW())
        RETURNING id;
      `, [cId, oId, rId, eId, dId, `especificaciones_p13_${suffix}.pdf`, operatorUserId]);
      const elId = linkRes.rows[0].id;

      return { cId, oId, dId, rId, eId, elId };
    }

    const seededApi = await seedCase('Expediente Real P13 API E2E', `api_${RUN_TAG}`);
    testCaseId = seededApi.cId;
    testOfferId = seededApi.oId;
    testDocId = seededApi.dId;
    testReqId = seededApi.rId;
    testEvidenceId = seededApi.eId;
    testEvidenceLinkId = seededApi.elId;

    const seededBrowser = await seedCase('Expediente Real P13 Browser E2E', `ui_${RUN_TAG}`);
    browserCaseId = seededBrowser.cId;
    browserOfferId = seededBrowser.oId;
    browserDocId = seededBrowser.dId;
    browserReqId = seededBrowser.rId;
    browserEvidenceId = seededBrowser.eId;
    browserEvidenceLinkId = seededBrowser.elId;
  });

  test.afterAll(async () => {
    const cleanupErrors: string[] = [];
    try {
      // 1. Restaurar plantilla a su estado previo [R2-07]
      if (templateBackup) {
        try {
          await dbClient.query(`
            UPDATE output_templates
            SET content = $1, checksum = $2, status = $3
            WHERE id = $4;
          `, [templateBackup.content, templateBackup.checksum, templateBackup.status, templateBackup.id]);
        } catch (err: any) {
          cleanupErrors.push(`restore_template: ${err.message}`);
        }
      } else {
        try {
          await dbClient.query(`
            DELETE FROM output_templates
            WHERE type = 'INFORME_TECNICO_EVALUACION' AND version = '1.0' AND entity_name = 'Abast-gp';
          `);
        } catch (err: any) {
          cleanupErrors.push(`delete_template: ${err.message}`);
        }
      }

      // 2. Limpieza estricta de expedientes creados
      const casesToClean = [testCaseId, browserCaseId].filter(Boolean);
      for (const cId of casesToClean) {
        try {
          await dbClient.query('DELETE FROM generated_outputs WHERE case_id = $1;', [String(cId)]);
          await dbClient.query('DELETE FROM offer_requirement_evidences WHERE case_id = $1;', [cId]);
          await dbClient.query('DELETE FROM offer_evaluations WHERE supplier_offer_id IN (SELECT id FROM supplier_offers WHERE case_id = $1);', [cId]);
          await dbClient.query('DELETE FROM offer_evidences WHERE supplier_offer_id IN (SELECT id FROM supplier_offers WHERE case_id = $1);', [cId]);
          await dbClient.query('DELETE FROM supplier_selection_final WHERE case_id = $1;', [cId]);
          await dbClient.query('DELETE FROM supplier_selection_attempts WHERE case_id = $1;', [cId]);
          await dbClient.query('DELETE FROM supplier_offers WHERE case_id = $1;', [cId]);
          await dbClient.query('DELETE FROM uploaded_documents WHERE case_id = $1;', [cId]);
          await dbClient.query('DELETE FROM case_requirement_matrices WHERE case_id = $1;', [cId]);
          await dbClient.query('DELETE FROM case_workflows WHERE case_id = $1;', [cId]);
          await dbClient.query('DELETE FROM case_files WHERE id = $1;', [cId]);
        } catch (err: any) {
          cleanupErrors.push(`case_${cId}_cleanup: ${err.message}`);
        }
      }

      if (supplierId) {
        try {
          await dbClient.query('DELETE FROM supplier_profiles WHERE supplier_id = $1;', [supplierId]);
          await dbClient.query('DELETE FROM suppliers WHERE id = $1;', [supplierId]);
        } catch (err: any) {
          cleanupErrors.push(`suppliers: ${err.message}`);
        }
      }

      if (operatorUserId || supervisorUserId) {
        try {
          await dbClient.query('DELETE FROM audit_logs WHERE user_id = $1 OR user_id = $2;', [operatorUserId || -1, supervisorUserId || -1]);
        } catch (err: any) {
          cleanupErrors.push(`audit_logs: ${err.message}`);
        }
      }

      // Comprobar que usuario preexistente NUNCA fue eliminado ni alterado por el test [Sección III]
      if (preexistingUserId) {
        const preCheck = await dbClient.query('SELECT id, username FROM users WHERE id = $1;', [preexistingUserId]);
        if (preCheck.rows.length === 0) {
          cleanupErrors.push('Regresión crítica: usuario preexistente fue eliminado indebidamente durante el test.');
        } else {
          // Limpiar usuario preexistente al final del teardown
          await dbClient.query('DELETE FROM users WHERE id = $1;', [preexistingUserId]);
        }
      }

      if (operatorUserId) {
        try {
          await dbClient.query('DELETE FROM users WHERE id = $1;', [operatorUserId]);
        } catch (err: any) {
          cleanupErrors.push(`operatorUser: ${err.message}`);
        }
      }

      try {
        await dbClient.query('DELETE FROM user_sessions WHERE id IN ($1, $2);', [OP_JTI, SUP_JTI]);
      } catch (err: any) {
        cleanupErrors.push(`userSessions: ${err.message}`);
      }

      if (supervisorUserId) {
        try {
          await dbClient.query('DELETE FROM users WHERE id = $1;', [supervisorUserId]);
        } catch (err: any) {
          cleanupErrors.push(`supervisorUser: ${err.message}`);
        }
      }

      if (realDocDiskPath && fs.existsSync(realDocDiskPath)) {
        try {
          fs.unlinkSync(realDocDiskPath);
        } catch (err: any) {
          cleanupErrors.push(`diskDoc: ${err.message}`);
        }
      }

      if (cleanupErrors.length > 0) {
        throw new Error(`Fallo crítico en teardown P13 E2E: ${cleanupErrors.join('; ')}`);
      }
    } finally {
      await dbClient.end();
    }
  });

  test('[API-INTEGRATION] Ciclo completo P13 contra backend real: Generación, SoD, Aprobación, PDF binario y Rechazo v2', async ({ playwright }) => {
    const opContext = await playwright.request.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${REAL_OP_JWT}` },
    });
    const supContext = await playwright.request.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${REAL_SUP_JWT}` },
    });

    // 1. Generación de informe técnico v1 por operador
    const genRes = await opContext.post(`/api/v6/cases/${testCaseId}/reports/p13/generate`, {
      data: { template_version: '1.0', idempotency_key: 'real-e2e-p13-key-01' },
    });
    expect(genRes.status()).toBe(200);
    const report1 = await genRes.json();
    expect(report1.version_number).toBe(1);
    expect(report1.status).toBe('GENERATED');
    expect(report1.snapshot_hash).toHaveLength(64);
    expect(report1.generated_by).toBe(operatorUserId);

    // 2. Envío a revisión formal
    const subRes = await opContext.post(`/api/v6/cases/${testCaseId}/reports/p13/${report1.id}/submit-review`);
    expect(subRes.status()).toBe(200);
    const subData = await subRes.json();
    expect(subData.status).toBe('UNDER_REVIEW');

    // 3. Verificación estricta de Roles y Segregación de Funciones (SoD)
    // a) El operador no tiene permisos para aprobar (RBAC 403)
    const opApproveRes = await opContext.post(`/api/v6/cases/${testCaseId}/reports/p13/${report1.id}/approve`, {
      data: { approval_notes: 'Intento de aprobacion por operador' },
    });
    expect(opApproveRes.status()).toBe(403);
    const opApproveErr = await opApproveRes.json();
    expect(opApproveErr.error?.message || opApproveErr.detail).toMatch(/permissions|autor|segregaci/i);

    // b) SoD genuina: un supervisor que generó su propio informe no puede auto-aprobarlo
    const supGenRes = await supContext.post(`/api/v6/cases/${testCaseId}/reports/p13/generate`, {
      data: { template_version: '1.0', idempotency_key: 'real-e2e-p13-sod-key' },
    });
    expect(supGenRes.status()).toBe(200);
    const supReport = await supGenRes.json();
    await supContext.post(`/api/v6/cases/${testCaseId}/reports/p13/${supReport.id}/submit-review`);

    const supAutoApproveRes = await supContext.post(`/api/v6/cases/${testCaseId}/reports/p13/${supReport.id}/approve`, {
      data: { approval_notes: 'Autoaprobacion indebida por supervisor autor' },
    });
    expect(supAutoApproveRes.status()).toBe(403);
    const supAutoApproveErr = await supAutoApproveRes.json();
    expect(supAutoApproveErr.detail || supAutoApproveErr.error?.message).toMatch(/separación de funciones|autor|sod/i);

    // 4. Aprobación legítima por supervisor independiente
    const supApproveRes = await supContext.post(`/api/v6/cases/${testCaseId}/reports/p13/${report1.id}/approve`, {
      data: { approval_notes: 'Aprobación certificada por supervisor independiente en prueba real E2E.' },
    });
    expect(supApproveRes.status()).toBe(200);
    const approvedData = await supApproveRes.json();
    expect(approvedData.status).toBe('APPROVED');
    expect(approvedData.approved_by).toBe(supervisorUserId);
    expect(approvedData.has_pdf).toBe(true);
    expect(approvedData.pdf_hash).toHaveLength(64);
    expect(approvedData.html_hash).toHaveLength(64);

    // 5. Descarga y verificación binaria del PDF generado por ReportLab
    const pdfRes = await supContext.get(`/api/v6/cases/${testCaseId}/reports/p13/${report1.id}/export/pdf`);
    expect(pdfRes.status()).toBe(200);
    expect(pdfRes.headers()['content-type']).toBe('application/pdf');
    const pdfBuffer = await pdfRes.body();
    expect(pdfBuffer.subarray(0, 8).toString('utf-8')).toContain('%PDF-1.4');

    // Hash SHA-256 de los bytes descargados debe coincidir byte a byte con pdf_hash
    const downloadedHash = crypto.createHash('sha256').update(pdfBuffer).digest('hex');
    expect(downloadedHash).toBe(approvedData.pdf_hash);

    // 5.b Verificar que el HTML exportado contenga las 12 secciones canónicas de P13 [R3-07]
    const htmlRes = await supContext.get(`/api/v6/cases/${testCaseId}/reports/p13/${report1.id}/export/html`);
    expect(htmlRes.status()).toBe(200);
    const htmlText = await htmlRes.text();
    for (let s = 1; s <= 12; s++) {
      expect(htmlText).toContain(`section-${s}`);
    }

    // 5.c Adversario Sección III: Intento de descarga con pdf_hash = NULL debe devolver 500 fail-closed
    await dbClient.query('UPDATE generated_outputs SET pdf_hash = NULL WHERE id = $1', [report1.id]);
    const nullHashRes = await supContext.get(`/api/v6/cases/${testCaseId}/reports/p13/${report1.id}/export/pdf`);
    expect(nullHashRes.status()).toBe(500);
    // Restaurar pdf_hash legítimo
    await dbClient.query('UPDATE generated_outputs SET pdf_hash = $1 WHERE id = $2', [approvedData.pdf_hash, report1.id]);

    // 5.d Adversario Sección III: Comprobar que usuario preexistente permanece intacto
    const preCheckInTest = await dbClient.query('SELECT id, username FROM users WHERE id = $1', [preexistingUserId]);
    expect(preCheckInTest.rows.length).toBe(1);
    expect(preCheckInTest.rows[0].username).toBe(PREEXISTING_USER);

    // 6. Verificación de integridad criptográfica vía endpoint dedicado
    const integRes = await supContext.get(`/api/v6/cases/${testCaseId}/reports/p13/${report1.id}/integrity`);
    expect(integRes.status()).toBe(200);
    const integData = await integRes.json();
    expect(integData.is_authentic).toBe(true);
    expect(integData.snapshot_intact).toBe(true);
    expect(integData.html_intact).toBe(true);
    expect(integData.pdf_intact).toBe(true);
    expect(integData.pdf_file_exists).toBe(true);

    // 7. Flujo de nueva versión subsiguiente y rechazo motivado
    const gen2Res = await opContext.post(`/api/v6/cases/${testCaseId}/reports/p13/generate`, {
      data: { template_version: '1.0', idempotency_key: 'real-e2e-p13-key-02' },
    });
    expect(gen2Res.status()).toBe(200);
    const report2 = await gen2Res.json();
    expect(report2.version_number).toBe(3);
    expect(report2.status).toBe('GENERATED');

    await opContext.post(`/api/v6/cases/${testCaseId}/reports/p13/${report2.id}/submit-review`);

    const rejectRes = await supContext.post(`/api/v6/cases/${testCaseId}/reports/p13/${report2.id}/reject`, {
      data: { rejection_reason: 'Falta adjuntar el plan de contingencia del servicio técnico.' },
    });
    expect(rejectRes.status()).toBe(200);
    const rejectedData = await rejectRes.json();
    expect(rejectedData.status).toBe('REJECTED');
    expect(rejectedData.rejected_by).toBe(supervisorUserId);
    expect(rejectedData.rejection_reason).toBe('Falta adjuntar el plan de contingencia del servicio técnico.');
  });

  test('[E2E-BROWSER-REAL] Flujo integral en navegador real interactuando con CaseResult y TechnicalReportPanel contra backend y PostgreSQL auténticos [R2-06] [R3-07]', async ({ page }) => {
    // 1. Configurar sesión de Operador en navegador real sin mocks de ruta
    await page.goto('/login');
    await page.evaluate(({ token, userObj }) => {
      sessionStorage.setItem('access_token', token);
      sessionStorage.setItem('user', JSON.stringify(userObj));
      localStorage.setItem('access_token', token);
      localStorage.setItem('user', JSON.stringify(userObj));
    }, {
      token: REAL_OP_JWT,
      userObj: { id: operatorUserId, username: OPERATOR_USER, role: 'OPERATOR' }
    });

    // 2. Navegación directa al expediente real fresco [R3-07]
    await page.goto(`/expedientes/${browserCaseId}`);
    await page.waitForSelector('button:has-text("Resultado")', { timeout: 20000 });
    await page.click('button:has-text("Resultado")');

    // 3. Inspeccionar panel P13 cargado desde el backend real
    await expect(page.locator('text=Informe Técnico de Evaluación y Selección (P13)')).toBeVisible({ timeout: 15000 });

    // 4. Generación obligatoria del nuevo informe desde la UI en expediente fresco [R3-07]
    const generateNewBtn = page.locator('button:has-text("Generar Nuevo Informe")');
    await expect(generateNewBtn).toBeVisible({ timeout: 15000 });
    await generateNewBtn.click();

    // 5. Verificar que el borrador v1 fue generado y aparece en la UI
    await expect(page.locator('button.tech-report-tab:has-text("Versión 1")')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.tech-report-card').getByText('Borrador (Generado)')).toBeVisible({ timeout: 15000 });

    // 6. Enviar a revisión formal desde la UI
    const submitReviewBtn = page.locator('button:has-text("Enviar a Revisión Formal")');
    await expect(submitReviewBtn).toBeVisible({ timeout: 15000 });
    await submitReviewBtn.click();
    await expect(page.locator('.tech-report-card').getByText('En Revisión Formal')).toBeVisible({ timeout: 15000 });

    // 7. Demostración de SoD en UI: El operador (autor) NO tiene el botón de aprobación
    await expect(page.locator('button:has-text("Aprobar Informe")')).not.toBeVisible();

    // 8. Cambiar identidad en el navegador a Supervisor independiente
    await page.evaluate(({ token, userObj }) => {
      sessionStorage.setItem('access_token', token);
      sessionStorage.setItem('user', JSON.stringify(userObj));
      localStorage.setItem('access_token', token);
      localStorage.setItem('user', JSON.stringify(userObj));
    }, {
      token: REAL_SUP_JWT,
      userObj: { id: supervisorUserId, username: SUPERVISOR_USER, role: 'SUPERVISOR' }
    });

    await page.reload();
    await page.waitForSelector('button:has-text("Resultado")', { timeout: 20000 });
    await page.click('button:has-text("Resultado")');

    // 9. Ahora como Supervisor, el botón 'Aprobar Informe' debe estar presente y funcional
    const approveBtn = page.locator('button:has-text("Aprobar Informe")');
    await expect(approveBtn).toBeVisible({ timeout: 15000 });
    await approveBtn.click();
    await expect(page.locator('text=Aprobar Informe Técnico')).toBeVisible({ timeout: 10000 });
    await page.fill('textarea[placeholder*="Ejemplo: Se certifica"]', 'Certificación técnica emitida por supervisor independiente en prueba E2E Browser real.');
    await page.click('button:has-text("Confirmar Aprobación")');
    await expect(page.locator('.tech-report-card').getByText('Aprobado y Certificado')).toBeVisible({ timeout: 20000 });

    // 10. Verificar presencia de descarga de PDF Certificado
    await expect(page.locator('button:has-text("Descargar PDF Certificado")')).toBeVisible({ timeout: 15000 });

    // 11. Verificar modal de autenticidad criptográfica en navegador real
    await page.click('button:has-text("Verificar Autenticidad")');
    await expect(page.locator('text=Certificación Criptográfica de Autenticidad')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Autenticidad Criptográfica Verificada')).toBeVisible({ timeout: 10000 });
    await page.locator('.tech-report-modal button:has-text("Cerrar")').click();

    // 12. Descarga auténtica del PDF generado por ReportLab y validación de hash contra PostgreSQL
    const downloadPromise = page.waitForEvent('download', { timeout: 20000 });
    await page.click('button:has-text("Descargar PDF Certificado")');
    const download = await downloadPromise;
    const downloadStream = await download.createReadStream();
    const chunks: Buffer[] = [];
    if (downloadStream) {
      for await (const chunk of downloadStream) {
        chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : chunk);
      }
    }
    const downloadedPdfBuffer = Buffer.concat(chunks);
    expect(downloadedPdfBuffer.length).toBeGreaterThan(100);
    expect(downloadedPdfBuffer.subarray(0, 8).toString('utf-8')).toContain('%PDF-1.4');

    // Correlación estricta con hash registrado en PostgreSQL
    const dbReportRes = await dbClient.query(`
      SELECT pdf_hash, html_hash, snapshot_hash FROM generated_outputs
      WHERE case_id = $1 AND report_kind = 'INFORME_TECNICO_EVALUACION' AND status = 'APPROVED'
      ORDER BY version_number DESC LIMIT 1;
    `, [String(browserCaseId)]);
    expect(dbReportRes.rows.length).toBeGreaterThan(0);
    const expectedPdfHash = dbReportRes.rows[0].pdf_hash;
    const actualDownloadedHash = crypto.createHash('sha256').update(downloadedPdfBuffer).digest('hex');
    expect(actualDownloadedHash).toBe(expectedPdfHash);
    expect(dbReportRes.rows[0].html_hash).toHaveLength(64);
    expect(dbReportRes.rows[0].snapshot_hash).toHaveLength(64);
  });
});

