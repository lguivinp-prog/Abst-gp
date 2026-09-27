import { test, expect } from '@playwright/test';

// Base64 valid PDF buffers with structural sections conforming to DocumentExtractionAgent
const REQ_PDF_BASE64 = 'JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDkyNTE5NDA1MSswMCcwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDkyNTE5NDA1MSswMCcwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmllZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMTg3Cj4+CnN0cmVhbQpHYXMyQDRVXStcKGtoWV9NQXQqPmsldVY4YSthaiNENl5gazAjPW4rK2coSXVydTglbEs/MWs8R1A8KEMiT1l0QipbaGxbIitfKSgkZC5IO0kiXkstalJlaycmRDZGU2ZPSXBebzBxNCtVZkdNT3BtTWk7O1RpZWFeNFNBWmFFL1JTN2NCZj0pLj9xPkYqPDBURWxkKiVrL2w4KTBdU2M5PiFBKWRkV0NcWmBvYHVpIVlFJEY0U0NTdH4+ZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgOAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNjEgMDAwMDAgbiAKMDAwMDAwMDkwMiAwMDAwMCBuIAowMDAwMDAwMTk5IDAwMDAwIG4gCjAwMDAwMDA0MDIgMDAwMDAgbiAKMDAwMDAwMDQ3MCAwMDAwMCBuIAowMDAwMDAwNzMxIDAwMDAwIG4gCjAwMDAwMDA3OTAgMDAwMDAgbiAKdHJhaWxlcgo8PAovSUQgCls8OWE5YzVkNTEzMGQ4ZjVmZTAwZTEwMDE5OGU1N2JhNmU+PDlhOWM1ZDUxMzBkOGY1ZmUwMGUxMDAxOThlNTdiYTZlPl0KJSBSZXBvcnRMYWIgZ2VuZXJhdGVkIFBERiBkb2N1bWVudCAtLSBkaWdlc3QgKG9wZW5zb3VyY2UpCgovSW5mbyA1IDAgUgovUm9vdCA0IDAgUgovU2l6ZSA4Cj4+CnN0YXJ0eHJlZgoxMDY3CiUlRU9GCg==';
const QUOT_PDF_BASE64 = 'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjcuMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjcuMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4NDJdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDI3NC9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeNp1kD9PBCEQxXs+BbWJyvwDN7lYGG3sTOguFptdiIUWNvf5783EeF5hWIZh3rwfLOk7PfVEuWBQboyPc/9K9x/j85SJcp/5eFDRaaqLrUrIF506uHhVdzXjqJFuj+/9NZV8S3ZHpLk/p+PBCvRpVQ1DkbGs8DpNUGI42QwxNCUuVpyJGumIvfipwe43uE1o4hRhKaJiUqXJgyzYkfCl85IJ8XBy3Sq1tU4uVashWh1NG2NtlYJJYqEu6BRkUgku9KFG6FzgHn/I7GRtoZHT3PlDYvj3ak18XrkkXFuLcxv/fx/103eQxTV/9d8eKFdMDeZeZ9wC/+gRE31OMuEZb2a84aUweHgMwktPb+kMpKp3gAplbmRzdHJlYW0KZW5kb2JqCgp4cmVmCjAgNwowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNDIgMDAwMDAgbiAKMDAwMDAwMDEyMCAwMDAwMCBuIAowMDAwMDAwMTcyIDAwMDAwIG4gCjAwMDAwMDAyMTMgMDAwMDAgbiAKMDAwMDAwMDMyMCAwMDAwMCBuIAowMDAwMDAwNDA5IDAwMDAwIG4gCgp0cmFpbGVyCjw8L1NpemUgNy9Sb290IDEgMCBSL0lEWzxDM0EyNUJDMzkzQzNBRjBEQzJCNTNBNzUzRjFFQzJBMD48MThCQkIxMTNBRTFDMUFFNERGODhEMzIzQ0Y1QzBCRDU+XT4+CnN0YXJ0eHJlZgo3NTIKJSVFT0YK';

test.describe('Document Intelligence E2E - Happy Path', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should complete the full happy path', async ({ page }) => {
    page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
    page.on('request', request => {
      if (request.url().includes('upload') || request.url().includes('documents')) {
        console.log(`REQUEST: ${request.method()} ${request.url()} HEADERS: ${JSON.stringify(request.headers())}`);
      }
    });
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
    await page.selectOption('select[name="contract_type"]', 'bienes');
    await expect(page.locator('select[name="contract_type"]')).toHaveValue('bienes');
    const modal = page.locator('h2:has-text("Nuevo Expediente")').locator('..');
    await expect(modal).toBeVisible();
    const submitBtn = modal.getByRole('button', { name: 'Crear Expediente', exact: true });
    await expect(submitBtn).toBeVisible();
    await submitBtn.click();

    // We should see it in the list and click it
    await expect(page.locator('text=E2E Test Case').first()).toBeVisible({ timeout: 15000 });
    await page.click('text=E2E Test Case');

    // 3. Upload Requirement with valid structural PDF
    await page.click('button:has-text("Cargar requerimiento")');
    await page.setInputFiles('input[type="file"][data-testid="upload-requirement"]', {
      name: 'req.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(REQ_PDF_BASE64, 'base64')
    });
    await page.click('button:has-text("Subir PDF")');

    // Check processing state
    await expect(page.locator('text=Procesando requerimiento').first()).toBeVisible({ timeout: 15000 });

    // 4. Esperar extracción y extraer requerimientos (V6)
    // Wait for the button 'Extraer requerimientos' which appears when extraction_ready is true
    await expect(page.locator('button:has-text("Extraer requerimientos")').first()).toBeVisible({ timeout: 90000 });
    await page.click('button:has-text("Extraer requerimientos")');
    await expect(page.locator('text=Requerimientos extraídos/verificados').first()).toBeVisible({ timeout: 30000 });

    // 5. Vincular Proveedor (V6)
    await page.click('button:has-text("Proveedores")');
    await page.click('button:has-text("Vincular Proveedor")');
    await page.fill('input[name="ruc"]', '20123456789');
    await page.fill('input[name="business_name"]', 'Proveedor E2E');
    await page.click('button:has-text("Vincular")');
    await expect(page.locator('text=Proveedor E2E').first()).toBeVisible({ timeout: 15000 });

    // 6. Subir Cotización en Ofertas (V6)
    await page.click('button:has-text("Ofertas")');
    await page.click('button:has-text("Editar")');
    await page.setInputFiles('input[type="file"]', {
      name: 'quot.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from(QUOT_PDF_BASE64, 'base64')
    });
    await page.fill('input[name="price"]', '1500');
    await page.selectOption('select[name="status"]', 'APPROVED');
    await page.click('button:has-text("Guardar")');
    await expect(page.locator('text=Oferta completada').first()).toBeVisible({ timeout: 15000 });

    // 7. Evaluar Oferta (V6)
    await page.click('button:has-text("Evaluación")');
    await page.click('button:has-text("Evaluar Oferta")');
    await expect(page.locator('text=Resultados de Requisitos').first()).toBeVisible({ timeout: 60000 });

    // 8. Proponer Selección (V6)
    await page.click('button:has-text("Selección")');
    await page.click('button:has-text("Proponer Selección")');
    await expect(page.locator('text=Selección Propuesta').first()).toBeVisible({ timeout: 15000 });

    // 9. Adjudicar (V6)
    await page.click('button:has-text("Resultado")');
    await page.click('button:has-text("Aprobar y Adjudicar")');
    await expect(page.locator('text=Expediente Adjudicado').first()).toBeVisible({ timeout: 15000 });
  });
});
