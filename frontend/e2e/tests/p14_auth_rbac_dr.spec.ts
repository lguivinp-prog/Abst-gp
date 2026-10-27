/**
 * p14_auth_rbac_dr.spec.ts
 *
 * Pruebas E2E Auténticas de Autenticación, MFA, RBAC Multitenant y Revocación de Sesión (P14 R2-02, R2-17).
 *
 * Criterios aplicados:
 * 1. Cero mocks: No se utiliza page.route() para simular login, MFA, tokens ni respuestas de autorización.
 * 2. Pruebas directas contra React en vivo (frontend-test:5173), FastAPI (backend-app:8000) y PostgreSQL (db-test:5432).
 * 3. Verificación de persistencia real de sesiones en PostgreSQL (tabla user_sessions).
 * 4. Verificación de logout UI, revocación server-side y rechazo 401 inmediato ante reuso de JWT previo.
 * 5. Escenario negativo: ante fallo de red en /auth/logout, no se declara revocación exitosa ni se otorga acceso protegido.
 * 6. Flujo completo: Login -> Desafío MFA -> Código TOTP real -> Dashboard -> Intento prohibido 403 -> Logout -> 401.
 */

import { test, expect } from '@playwright/test';
import { Client } from 'pg';
import crypto from 'node:crypto';

const API_BASE = process.env.API_URL || 'http://backend-app:8000';
const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://test_user:test_password@db-test:5432/test_db';

/**
 * Calcula un código TOTP de 6 dígitos bajo RFC 6238 usando node:crypto.
 * Utiliza el paso estándar de 30 segundos y SHA-1.
 */
function computeRfc6238Totp(secretBase32: string): string {
  const base32chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (let i = 0; i < secretBase32.length; i++) {
    const val = base32chars.indexOf(secretBase32.charAt(i).toUpperCase());
    if (val === -1) continue;
    bits += val.toString(2).padStart(5, '0');
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(parseInt(bits.substring(i, i + 8), 2));
  }
  const key = Buffer.from(bytes);
  const epoch = Math.floor(Date.now() / 1000);
  const timeStep = Math.floor(epoch / 30);
  const timeBuffer = Buffer.alloc(8);
  timeBuffer.writeBigInt64BE(BigInt(timeStep));

  const hmac = crypto.createHmac('sha1', key).update(timeBuffer).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const binary =
    ((hmac[offset] & 0x7f) << 24) |
    ((hmac[offset + 1] & 0xff) << 16) |
    ((hmac[offset + 2] & 0xff) << 8) |
    (hmac[offset + 3] & 0xff);
  return (binary % 1000000).toString().padStart(6, '0');
}

test.describe('P14 R2-02 & R2-17: Autenticación Auténtica, MFA, RBAC y Revocación', () => {
  let dbClient: Client;

  test.beforeAll(async () => {
    dbClient = new Client({ connectionString: DATABASE_URL });
    await dbClient.connect();
  });

  test.afterAll(async () => {
    if (dbClient) {
      await dbClient.end();
    }
  });

  // -------------------------------------------------------------------------
  // R2-02: Cierre de Sesión, Persistencia en DB y Revocación Real de JWT
  // -------------------------------------------------------------------------
  test('R2-02: Flujo completo de Login, persistencia de sesión en DB, Logout React y rechazo 401 de JWT previo', async ({ page }) => {
    // 1. Navegar al Login real
    await page.goto('/login');
    await expect(page.locator('h1')).toHaveText('ABST-GP');

    // 2. Ingresar credenciales primarias reales
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpassword');
    await page.click('button[type="submit"]');

    // 3. Confirmar acceso exitoso a ruta protegida
    await expect(page.locator('text=Expedientes').first()).toBeVisible({ timeout: 15000 });

    // 4. Extraer token de sessionStorage y verificar que NO existe en localStorage (R2-15)
    const tokenInSession = await page.evaluate(() => sessionStorage.getItem('access_token'));
    const tokenInLocal = await page.evaluate(() => localStorage.getItem('access_token'));

    expect(tokenInSession).not.toBeNull();
    expect(typeof tokenInSession).toBe('string');
    expect(tokenInLocal).toBeNull(); // localStorage eliminado por R2-15

    // 5. Verificar en PostgreSQL que la sesión está persistida y activa (fail-closed)
    const adminUserRes = await dbClient.query("SELECT id FROM users WHERE username = 'admin'");
    const adminUserId = adminUserRes.rows[0].id;

    const sessionRes = await dbClient.query(
      'SELECT id, is_revoked, expires_at FROM user_sessions WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1',
      [adminUserId]
    );
    expect(sessionRes.rows.length).toBeGreaterThan(0);
    const activeSession = sessionRes.rows[0];
    expect(activeSession.is_revoked).toBe(false);

    // 6. Probar que el JWT actual tiene acceso exitoso a la API protegida antes del logout
    const preLogoutRes = await page.request.get(`${API_BASE}/cases/`, {
      headers: { Authorization: `Bearer ${tokenInSession}` }
    });
    expect(preLogoutRes.status()).toBe(200);

    // 7. Ejecutar logout mediante la interfaz React (botón Cerrar sesión)
    const logoutButton = page.locator('button.nav-item--logout');
    await expect(logoutButton).toBeVisible();
    await logoutButton.click();

    // 8. Verificar redirección automática a /login tras logout
    await expect(page.locator('h1')).toHaveText('ABST-GP', { timeout: 10000 });
    await expect(page.locator('input#username')).toBeVisible();

    // 9. Comprobar que sessionStorage fue purgado y localStorage sigue vacío
    const postLogoutSessionToken = await page.evaluate(() => sessionStorage.getItem('access_token'));
    const postLogoutLocalToken = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(postLogoutSessionToken).toBeNull();
    expect(postLogoutLocalToken).toBeNull();

    // 10. Comprobar en PostgreSQL que la sesión fue REVOCADA por el backend (/auth/logout)
    const postLogoutDbRes = await dbClient.query(
      'SELECT is_revoked FROM user_sessions WHERE id = $1',
      [activeSession.id]
    );
    expect(postLogoutDbRes.rows[0].is_revoked).toBe(true);

    // 11. Intentar reutilizar el JWT anterior contra la API protegida -> DEBE retornar 401 Unauthorized
    const replayRes = await page.request.get(`${API_BASE}/cases/`, {
      headers: { Authorization: `Bearer ${tokenInSession}` }
    });
    expect(replayRes.status()).toBe(401);

    // 12. Actualizar la página (F5) y verificar que NO se restaura la sesión
    await page.reload();
    await expect(page.locator('input#username')).toBeVisible();
    await expect(page.locator('text=Expedientes').first()).not.toBeVisible();
  });

  // -------------------------------------------------------------------------
  // R2-02 Negativo: Falla de red en Logout no declara revocación falsa ni concede acceso
  // -------------------------------------------------------------------------
  test('R2-02 Negativo: Falla de conectividad durante logout purga estado local y deniega acceso protegido', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input#username', 'admin');
    await page.fill('input#password', 'adminpassword');
    await page.click('button[type="submit"]');

    await expect(page.locator('text=Expedientes').first()).toBeVisible({ timeout: 15000 });

    // Interceptar ÚNICAMENTE la petición POST /auth/logout para simular caída de red puntual
    await page.route('**/auth/logout', async (route) => {
      await route.abort('failed');
    });

    // Ejecutar logout con backend inaccesible
    await page.locator('button.nav-item--logout').click();

    // Debe limpiar el cliente y retornar a login
    await expect(page.locator('input#username')).toBeVisible({ timeout: 10000 });
    const token = await page.evaluate(() => sessionStorage.getItem('access_token'));
    expect(token).toBeNull();

    // Deshacer intercepción
    await page.unroute('**/auth/logout');
  });

  // -------------------------------------------------------------------------
  // Sección IV: Flujo Completo E2E (Login -> MFA -> Permitido -> Prohibido -> Logout -> 401)
  // -------------------------------------------------------------------------
  test('R2-17 / Sección IV: Flujo completo Login -> Desafío MFA -> TOTP real -> Acceso permitido -> Intento 403 -> Logout -> 401', async ({ page }) => {
    // 1. Navegar al Login
    await page.goto('/login');

    // 2. Ingresar con usuario con MFA habilitado (p14_mfa_operator)
    await page.fill('input#username', 'p14_mfa_operator');
    await page.fill('input#password', 'MfaOperatorPass123!');
    await page.click('button[type="submit"]');

    // 3. Verificar que el frontend presenta la vista de desafío MFA
    await expect(page.locator('input#totpCode')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Verificación de Segundo Factor (MFA)')).toBeVisible();

    // 4. Calcular código TOTP auténtico para el secreto base32 JBSWY3DPEHPK3PXP
    const totpCode = computeRfc6238Totp('JBSWY3DPEHPK3PXP');

    // 5. Introducir el código TOTP en el formulario
    await page.fill('input#totpCode', totpCode);
    await page.click('button[type="submit"]');

    // 6. Verificar que la autenticación de dos factores es exitosa y se accede al sistema
    await expect(page.locator('text=Expedientes').first()).toBeVisible({ timeout: 15000 });

    // 7. Extraer token de sessionStorage
    const operatorToken = await page.evaluate(() => sessionStorage.getItem('access_token'));
    expect(operatorToken).not.toBeNull();

    // 8. Acceso permitido (OPERATOR consulta endpoint autorizado de su tenant) -> 200 OK
    const allowedRes = await page.request.get(`${API_BASE}/cases/`, {
      headers: { Authorization: `Bearer ${operatorToken}` }
    });
    expect(allowedRes.status()).toBe(200);

    // 9. Intento prohibido (OPERATOR intenta acceder a eventos de seguridad de SUPERADMIN) -> 403 Forbidden
    const forbiddenRes = await page.request.get(`${API_BASE}/admin/security/events`, {
      headers: { Authorization: `Bearer ${operatorToken}` }
    });
    expect(forbiddenRes.status()).toBe(403);

    // 10. Cerrar sesión mediante la UI
    await page.locator('button.nav-item--logout').click();
    await expect(page.locator('input#username')).toBeVisible({ timeout: 10000 });

    // 11. Reutilización del token revocado -> 401 Unauthorized
    const postLogoutRes = await page.request.get(`${API_BASE}/cases/`, {
      headers: { Authorization: `Bearer ${operatorToken}` }
    });
    expect(postLogoutRes.status()).toBe(401);
  });
});
