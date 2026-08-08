import { test, expect } from '@playwright/test';

// Base64 valid PDF buffers with structural sections conforming to DocumentExtractionAgent
const REQ_PDF_BASE64 = 'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4NDJdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDMwOS9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeNp1UbtOBDEM7PMVqZGA+BlFOlEgaOiQ0iGK015WFFDQ8P1MfO/itJuXxxmPJ+k3PfdEueCjXBk/5/6THr/G918myn3NHxttPLioa9OhpAtWxapcrJgpR0SUnj77Wyr5nuyBSHN/SR8bE7fK1b25YKxcXN0wk7NTlYpTIDsM84HzyiOY+h1qn3eosdexouJWUVibuYIRasAIFYRZgA9DQMmmSsE9RC54yLVSNW9Vjqp8nHQ1aBCgO1+r3FZy0IKuZyUV1DLsms1duGECf9pRke6joQWZcmYTmkxWfIEf2wuHwo3KWKuTbLkIiQXapnPYCVxcZh5ihMx27Z1waKyBUXiLm3FvRX94l+geHAd2Bjbj882uehcJpqWGlsq3NepUtAOnTGx2f8oBcuB87ek9/QNknZD7CmVuZHN0cmVhbQplbmRvYmoKCnhyZWYKMCA3CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA0MiAwMDAwMCBuIAowMDAwMDAwMTIwIDAwMDAwIG4gCjAwMDAwMDAxNzIgMDAwMDAgbiAKMDAwMDAwMDIxMyAwMDAwMCBuIAowMDAwMDAwMzIwIDAwMDAwIG4gCjAwMDAwMDA0MDkgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA3L1Jvb3QgMSAwIFIvSURbPEMyOEIxOUMzQUYxMkMyQkRDMzlCQzI5RTNGNzcyREMzPjxFMDFBRURENjdGRTI5RTRFMzczNjFGQjUzMDcyQTAwRj5dPj4Kc3RhcnR4cmVmCjc4NwolJUVPRgo=';
const QUOT_PDF_BASE64 = 'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4NDJdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDI3NC9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeNp1kD9PBCEQxXs+BbWJyvwDN7lYGG3sTOguFptdiIUWNvf5783EeF5hWIZh3rwfLOk7PfVEuWBQboyPc/9K9x/j85SJcp/5eFDRaaqLrUrIF506uHhVdzXjqJFuj+/9NZV8S3ZHpLk/p+PBCvRpVQ1DkbGs8DpNUGI42QwxNCUuVpyJGumIvfipwe43uE1o4hRhKaJiUqXJgyzYkfCl85IJ8XBy3Sq1tU4uVashWh1NG2NtlYJJYqEu6BRkUgku9KFG6FzgHn/I7GRtoZHT3PlDYvj3ak18XrkkXFuLcxv/fx/103eQxTV/9d8eKFdMDeZeZ9wC/+gRE31OMuEZb2a84aUweHgMwktPb+kMpKp3gAplbmRzdHJlYW0KZW5kb2JqCgp4cmVmCjAgNwowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAwMTcyIDAwMDAwIG4gCjAwMDAwMDAyMTMgMDAwMDAgbiAKMDAwMDAwMDMyMCAwMDAwMCBuIAowMDAwMDAwNDA5IDAwMDAwIG4gCgp0cmFpbGVyCjw8L1NpemUgNy9Sb290IDEgMCBSL0lEWzxDM0EyNUJDMzkzQzNBRjBEQzJCNTNBNzUzRjFFQzJBMD48MThCQkIxMTNBRTFDMUFFNERGODhEMzIzQ0Y1QzBCRDU+XT4+CnN0YXJ0eHJlZgo3NTIKJSVFT0YK';

test.describe('Document Intelligence E2E - Happy Path', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should complete the full happy path', async ({ page }) => {
    test.setTimeout(120000);

    // 1. Login
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'adminpassword');
    await page.click('button[type="submit"]');

    // Verify successful login
    await expect(page.locator('text=Expedientes').first()).toBeVisible({ timeout: 15000 });

    // 2. Create Case
    await page.click('button:has-text("Nuevo Expediente")');
    await page.fill('input[name="title"]', 'E2E Test Case');
    await page.fill('input[name="contract_type"]', 'Standard');
    await page.click('button:has-text("Crear")');

    // We should see it in the list and click it
    await expect(page.locator('text=E2E Test Case').first()).toBeVisible({ timeout: 15000 });
    await page.click('text=E2E Test Case');

    // 3. Upload Requirement with valid structural PDF
    await page.setInputFiles('input[type="file"][data-testid="upload-requirement"]', {
      name: 'req.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(REQ_PDF_BASE64, 'base64')
    });
    await page.click('button:has-text("Subir PDF")');
    
    // Check processing state and wait for sections to appear
    await expect(page.locator('text=Procesando OCR').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=Secciones Detectadas').first()).toBeVisible({ timeout: 90000 });

    // 4. Confirm Sections
    await page.click('button:has-text("Confirmar Secciones y Continuar")');

    // 5. Upload Quotation with valid conditions PDF
    await page.setInputFiles('input[type="file"][data-testid="upload-quotation"]', {
      name: 'quot.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(QUOT_PDF_BASE64, 'base64')
    });
    await page.click('button:has-text("Subir Cotización")');
    
    // Wait for comparison button to be ready
    await expect(page.locator('button:has-text("Ejecutar Comparación")')).toBeEnabled({ timeout: 90000 });

    // 6. Run Comparison
    await page.click('button:has-text("Ejecutar Comparación")');
    
    // Check results table
    await expect(page.locator('table').first()).toBeVisible({ timeout: 90000 });

    // 7. Generate Document
    await page.click('button:has-text("Generar Anexo Final")');
    
    await expect(page.locator('button:has-text("Descargar Anexo HTML")')).toBeVisible({ timeout: 30000 });

    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 60000 }),
      page.click('button:has-text("Descargar Anexo HTML")')
    ]);
    expect(download.suggestedFilename()).toContain('.html');
  });
});
