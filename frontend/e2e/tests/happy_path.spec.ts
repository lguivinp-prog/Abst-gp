import { test, expect } from '@playwright/test';
import { Client } from 'pg';
import zlib from 'zlib';

/**
 * Extrae texto legible a partir de los streams de un archivo PDF sintético en buffer
 */
function extractPdfText(pdfBuffer: Buffer): string {
  const content = pdfBuffer.toString('binary');
  const streamRegex = /stream\r?\n([\s\S]*?)\r?\nendstream/g;
  let match: RegExpExecArray | null;
  let fullText = '';
  while ((match = streamRegex.exec(content)) !== null) {
    let streamStr = '';
    try {
      streamStr = zlib.inflateSync(Buffer.from(match[1], 'binary')).toString('utf8');
    } catch {
      streamStr = match[1];
    }
    const decoded = streamStr.replace(/<([0-9a-fA-F]+)>/g, (_, hex) =>
      Buffer.from(hex, 'hex').toString('utf8')
    );
    fullText += decoded + '\n';
  }
  return fullText;
}

// Base64 valid PDF buffers with structural sections conforming to DocumentExtractionAgent
const REQ_PDF_BASE64 = 'JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNlcyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9JbWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRvYmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRhbG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0ZSAoRDoyMDI2MDkyNTE5NDA1MSswMCcwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3JkcyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDkyNTE5NDA1MSswMCcwMCcpIC9Qcm9kdWNlciAoUmVwb3J0TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmllZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoKPDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMTg3Cj4+CnN0cmVhbQpHYXMyQDRVXStcKGtoWV9NQXQqPmsldVY4YSthaiNENl5gazAjPW4rK2coSXVydTglbEs/MWs8R1A8KEMiT1l0QipbaGxbIitfKSgkZC5IO0kiXkstalJlaycmRDZGU2ZPSXBebzBxNCtVZkdNT3BtTWk7O1RpZWFeNFNBWmFFL1JTN2NCZj0pLj9xPkYqPDBURWxkKiVrL2w4KTBdU2M5PiFBKWRkV0NcWmBvYHVpIVlFJEY0U0NTdH4+ZW5kc3RyZWFtCmVuZG9iagp4cmVmCjAgOAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNjEgMDAwMDAgbiAKMDAwMDAwMDkwMiAwMDAwMCBuIAowMDAwMDAwMTk5IDAwMDAwIG4gCjAwMDAwMDA0MDIgMDAwMDAgbiAKMDAwMDAwMDQ3MCAwMDAwMCBuIAowMDAwMDAwNzMxIDAwMDAwIG4gCjAwMDAwMDA3OTAgMDAwMDAgbiAKdHJhaWxlcgo8PAovSUQgCls8OWE5YzVkNTEzMGQ4ZjVmZTAwZTEwMDE5OGU1N2JhNmU+PDlhOWM1ZDUxMzBkOGY1ZmUwMGUxMDAxOThlNTdiYTZlPl0KJSBSZXBvcnRMYWIgZ2VuZXJhdGVkIFBERiBkb2N1bWVudCAtLSBkaWdlc3QgKG9wZW5zb3VyY2UpCgovSW5mbyA1IDAgUgovUm9vdCA0IDAgUgovU2l6ZSA4Cj4+CnN0YXJ0eHJlZgoxMDY3CiUlRU9GCg==';

// Base64 valid commercial quotation PDF containing verifiable commitments matching the technical requirements
const QUOT_PDF_BASE64 = 'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjkuMAoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjkuMCk+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDU5NSA4NDJdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFIgNyAwIFIgOCAwIFIgOSAwIFIgMTAgMCBSIDExIDAgUiAxMiAwIFIgMTMgMCBSIDE0IDAgUiAxNSAwIFIgMTYgMCBSIDE3IDAgUiAxOCAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDEwMi9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeNodyLEKhEAMBNA+X5E/uE12oiyIxYGNnZBOLERdLM7imvv+izIMMzz60ttJOEWELXFblP2i13l8fizCXnnukFENKLZC4hdUHJpuxQ4zfUywhYVnzXcb3WNTln7xkQanif5WERjTCmVuZHN0cmVhbQplbmRvYmoKCjcgMCBvYmoKPDwvTGVuZ3RoIDkwL0ZpbHRlci9GbGF0ZURlY29kZT4+CnN0cmVhbQp42g3GIQ6AQAwEQN9X9Ae0pXtnCIIEgyOpIwgEFwQIDO+nGTP00hSkLEkZwrU6x0Pddd4fq3I03gYIzBuKI3nO+sMEUq20WgqS58zE0Ztj3GOhOWilH/6LFWMKZW5kc3RyZWFtCmVuZG9iagoKOCAwIG9iago8PC9MZW5ndGggODA+PgpzdHJlYW0KCnEKQlQKMSAwIDAgMSA1MCA3NTYgVG0KL2hlbHYgMTEgVGYgWzw1MjU1NDMzYTIwMzIzMDMxMzIzMzM0MzUzNjM3MzgzOT5dVEoKRVQKUQoKZW5kc3RyZWFtCmVuZG9iagoKOSAwIG9iago8PC9MZW5ndGggMTA1L0ZpbHRlci9GbGF0ZURlY29kZT4+CnN0cmVhbQp42i2KOwrDUAwEe51CN7A+K4LBpDC4cRdQF1K4eI8UcZHG57cMZmGLmaE/zUnKUlMO4YcJ507Dt/0OVuXs/J5crZkAiHB4GMYQOEZ03Ly+KALtauyyPVDdBi3fw317fnKlJelFJ/thGk0KZW5kc3RyZWFtCmVuZG9iagoKMTAgMCBvYmoKPDwvTGVuZ3RoIDE0Mi9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeNo1jL0KQjEMhfc8Rd7ApGkTCuIg3MVN6CZO3hYHHVx8fk+vSjhDvvNDLzo2UhacchEOSdyetLv3x5tVuQ2+7ItF8dWrd69hkSP5SOIFApvE1W+Q4R/ewfN0TU2SZANbQ6JsuewDfQ37p7yEuYHV+Hp1W1/Rgo/d+dl0Qn7djKyD98O1nWhpdKYPAEQuFQplbmRzdHJlYW0KZW5kb2JqCgoxMSAwIG9iago8PC9MZW5ndGggMTU0L0ZpbHRlci9GbGF0ZURlY29kZT4+CnN0cmVhbQp42kWOOw4CMQwFe5/CNyBOYpuVEAUSDR1SOkSBdhNRQEHD+XneLVCUjzzPE9OHTo2EE5awJrZ95fam3bO/vizCbfDtUIurLZ5stskWbLXu1UZOVmxYN7PhGURRqeupXpBX8Al0wi3rO9JgOaE/aN+Yl/LIqYYN/7iCCkxhlUhvVkwxg8QMgprHHLDlvzv3471d6NzoSj+b+DJJCmVuZHN0cmVhbQplbmRvYmoKCjEyIDAgb2JqCjw8L0xlbmd0aCA5MD4+CnN0cmVhbQoKcQpCVAoxIDAgMCAxIDUwIDY0OCBUbQovaGVsdiAxMSBUZiBbPDMyMmUyMDQzNDE0ZTU0NDk0NDQxNDQyMDU5MjA1MDUyNDU0MzQ5NGYzYT5dVEoKRVQKUQoKZW5kc3RyZWFtCmVuZG9iagoKMTMgMCBvYmoKPDwvTGVuZ3RoIDEwOS9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeNo1izsKAkEQRPM+Rd/A/sxUI4iBsImZ0JlssOAMBhqYeH5bRCqo4j2KXnRKUpaKcheGC+eTdvfxeLMq5+TroTkUIxr2aLWabyauLibRMf4UPdzk2yb1mLhF+fi5GQYtP45rnmlJutAHmtobeAplbmRzdHJlYW0KZW5kb2JqCgoxNCAwIG9iago8PC9MZW5ndGggMTA5L0ZpbHRlci9GbGF0ZURlY29kZT4+CnN0cmVhbQp42h2KMQpCQQxE+5wiN3CSbGYRxEKwsRPSiYXILhZa2Hh+l88wD+Yx8pVTiSlWTBNKc62P7F7j/VMzram3Q6I7k8E9p6M3zlXj08FJMrtve/l4ODJ8vcIiAwEfG5Fo2YaP470uci65yh+zuxvhCmVuZHN0cmVhbQplbmRvYmoKCjE1IDAgb2JqCjw8L0xlbmd0aCA5Ni9GaWx0ZXIvRmxhdGVEZWNvZGU+PgpzdHJlYW0KeNo1iTEKgEAMBPu8Ij/wctkoglgINnZCOrEQObHQwsb3ewqyxQyzdFHnJBzyhC2wVSX7ScWejptF2DeeGtWYYoBiQwJQZ6s/N9O/GyxCoJmWub6fLu3sA/VOIz30kRgeCmVuZHN0cmVhbQplbmRvYmoKCjE2IDAgb2JqCjw8L0xlbmd0aCAxMTAvRmlsdGVyL0ZsYXRlRGVjb2RlPj4Kc3RyZWFtCnjaHYsxCgJRDET7nCI3MPOzyXdBLAQbu4V0i8Uif7HQwsbzO0ggGSbvyUcuJVDjQMM04qj1lsNzvL4KaO26nsLykehb7s1yyuCOHH3qjbcnfGvm8Ph/Z5LO5Ala5NiB5Ex7nO91k2vJIj9/KhtyCmVuZHN0cmVhbQplbmRvYmoKCjE3IDAgb2JqCjw8L0xlbmd0aCAxMDIvRmlsdGVyL0ZsYXRlRGVjb2RlPj4Kc3RyZWFtCnjaFck7CsMwEIThfk+xN8g+pBGGkCLgxp1hO+PC2DIp7CJNzh+J4W++oS+9g5SlTTkL5yQcNz0+9fqxKsfJyzMVaDEoakkYoCZwnDiQm3oX7L6ZuHlqX3fvWX2tMdEYNNMf3wUXzQplbmRzdHJlYW0KZW5kb2JqCgoxOCAwIG9iago8PC9MZW5ndGggMTEzL0ZpbHRlci9GbGF0ZURlY29kZT4+CnN0cmVhbQp42h2KMQoCQQxF+5wiN3CSmfwwIBbCNnZCOrGQcRYLLWz2/Gblwy/ee/Slc5BwyQlbYVPl+NDhNd8bi3CsfDu24QaHuGpBg+UbpjdX/Hl9aGmCgScEdXdZ9CyqN/TsLGnHipl+6Dzd40JL0JV+JPIdJgplbmRzdHJlYW0KZW5kb2JqCgp4cmVmCjAgMTkKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDQyIDAwMDAwIG4gCjAwMDAwMDAxMjAgMDAwMDAgbiAKMDAwMDAwMDE3MiAwMDAwMCBuIAowMDAwMDAwMjEzIDAwMDAwIG4gCjAwMDAwMDA0MDEgMDAwMDAgbiAKMDAwMDAwMDQ5MCAwMDAwMCBuIAowMDAwMDAwNjYxIDAwMDAwIG4gCjAwMDAwMDA4MTkgMDAwMDAgbiAKMDAwMDAwMDk0OCAwMDAwMCBuIAowMDAwMDAxMTIyIDAwMDAwIG4gCjAwMDAwMDEzMzQgMDAwMDAgbiAKMDAwMDAwMTU1OCAwMDAwMCBuIAowMDAwMDAxNjk4IDAwMDAwIG4gCjAwMDAwMDE4NzcgMDAwMDAgbiAKMDAwMDAwMjA1NiAwMDAwMCBuIAowMDAwMDAyMjIxIDAwMDAwIG4gCjAwMDAwMDI0MDEgMDAwMDAgbiAKMDAwMDAwMjU3MyAwMDAwMCBuIAoKdHJhaWxlcgo8PC9TaXplIDE5L1Jvb3QgMSAwIFIvSURbPEMzQTU2QkMzOTlDMkI0QzJCNzREMjgwMTExQzJCRkMzPjxCQUVDNTdGOEY5RDRBODkwNTE0OEM5MTdFQUE0RUE5MT5dPj4Kc3RhcnR4cmVmCjI3NTYKJSVFT0YK';

/**
 * Prepara de manera segura y estrictamente aislada las precondiciones de base de datos
 * para la oferta y proveedor vinculados al expediente creado por el escenario,
 * registrando evidencias reales vinculadas al documento fuente sin omitir auditoría.
 */
export async function prepareHappyPathPreconditions(
  caseId: number,
  expectedTenantId: string,
  customConnStr?: string
) {
  const connStr = customConnStr || process.env.DATABASE_URL || 'postgresql://test_user:test_password@db-test:5432/test_db';

  // 1. Validar conexión al servicio autorizado de pruebas y no a un host arbitrario
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(connStr);
  } catch {
    throw new Error(`ABORT: Invalid database connection URL: ${connStr}`);
  }
  const authorizedHosts = ['db-test', 'localhost', '127.0.0.1'];
  if (!authorizedHosts.includes(parsedUrl.hostname)) {
    throw new Error(`ABORT: Database safety check failed. Unauthorized host '${parsedUrl.hostname}', strictly expected one of: ${authorizedHosts.join(', ')}`);
  }

  const dbClient = new Client({ connectionString: connStr });
  await dbClient.connect();

  try {
    // 2. Comprobar current_database() = 'test_db'
    const dbCheck = await dbClient.query('SELECT current_database() as db;');
    if (dbCheck.rows[0]?.db !== 'test_db') {
      throw new Error(`ABORT: Database safety check failed. Connected to '${dbCheck.rows[0]?.db}', strictly expected 'test_db'.`);
    }

    // 3. Validar que el expediente pertenece al tenant esperado
    const caseCheck = await dbClient.query(
      'SELECT id, tenant_id FROM case_files WHERE id = $1 AND tenant_id = $2;',
      [caseId, expectedTenantId]
    );
    if (caseCheck.rows.length === 0) {
      throw new Error(`ABORT: Security guard failed. Case ${caseId} does not belong to expected tenant '${expectedTenantId}' or does not exist.`);
    }

    // 4. Localizar ÚNICAMENTE la oferta y proveedor del expediente creado y tenant esperado
    const offRes = await dbClient.query(`
      SELECT so.id as offer_id, so.supplier_id
      FROM supplier_offers so
      JOIN case_files cf ON cf.id = so.case_id
      WHERE so.case_id = $1 AND cf.tenant_id = $2
      ORDER BY so.id DESC LIMIT 1;
    `, [caseId, expectedTenantId]);

    if (offRes.rows.length === 0) {
      throw new Error(`ABORT: No supplier offer found for case ${caseId} and tenant '${expectedTenantId}'.`);
    }

    const { offer_id: offerId, supplier_id: supplierId } = offRes.rows[0];

    // 5. Validar que el proveedor pertenece al tenant esperado
    const supCheck = await dbClient.query(
      'SELECT id FROM suppliers WHERE id = $1 AND tenant_id = $2;',
      [supplierId, expectedTenantId]
    );
    if (supCheck.rows.length === 0) {
      throw new Error(`ABORT: Supplier ${supplierId} does not belong to expected tenant '${expectedTenantId}'.`);
    }

    // 6. Configurar perfil verificado del proveedor
    await dbClient.query(`
      INSERT INTO supplier_profiles (supplier_id, validation_status)
      VALUES ($1, 'VERIFIED')
      ON CONFLICT (supplier_id) DO UPDATE SET validation_status = 'VERIFIED';
    `, [supplierId]);

    // 7. Identificar el UploadedDocument real de la cotización cargada durante la prueba para el expediente
    const docRes = await dbClient.query(`
      SELECT id, original_filename, stored_path
      FROM uploaded_documents
      WHERE case_id = $1 AND (original_filename = 'quot.pdf' OR document_type = 'oferta')
      ORDER BY id DESC LIMIT 1;
    `, [caseId]);

    if (docRes.rows.length === 0) {
      throw new Error(`ABORT: Uploaded quotation document not found for case ${caseId}.`);
    }
    const quotationDoc = docRes.rows[0];

    // 8. Identificar los requisitos extraídos y sus valores obligatorios
    const reqRes = await dbClient.query(`
      SELECT id, description, value, mandatory
      FROM case_requirement_matrices
      WHERE case_id = $1 AND mandatory = true
      ORDER BY id ASC;
    `, [caseId]);

    if (reqRes.rows.length === 0) {
      throw new Error(`ABORT: No mandatory requirements found for case ${caseId}.`);
    }
    const mandatoryReqs = reqRes.rows;

    // Extraer texto legible de la cotización para comprobación de presencia real
    const quotationPdfText = extractPdfText(Buffer.from(QUOT_PDF_BASE64, 'base64'));

    // 9. Registrar OfferEvidence asociado al UploadedDocument real con fragmentos procedentes de la cotización
    const createdEvidences: Array<{
      evidenceId: number;
      requirementId: number;
      documentId: number;
      fragment: string;
      page: number;
    }> = [];

    for (const req of mandatoryReqs) {
      let fragment = '';
      const descLower = (req.description || '').toLowerCase();
      if (descLower.includes('computadoras') || descLower.includes('bienes')) {
        fragment = 'Suministro e instalacion de 10 Computadoras de escritorio modelo corporativo.';
      } else if (descLower.includes('cantidad') || descLower.includes('10')) {
        fragment = 'Cantidad: 10 unidades de Computadoras.';
      } else {
        // CORRECCIÓN 1: Eliminar el fallback genérico. Fallar explícitamente si no hay acreditación documental
        throw new Error(
          `ABORT: No documentary evidence corresponding to mandatory requirement '${req.description}' (id: ${req.id}) found in quotation PDF.`
        );
      }

      // Comprobar estrictamente que el fragmento figura en el texto extraído del PDF cargado
      if (!quotationPdfText.includes(fragment)) {
        throw new Error(
          `ABORT: Documentary fragment '${fragment}' for requirement '${req.description}' does not exist in quotation PDF text.`
        );
      }

      const evInsert = await dbClient.query(`
        INSERT INTO offer_evidences (supplier_offer_id, document_id, document_type, fragment, confidence, page, created_at)
        VALUES ($1, $2, 'FICHA_TECNICA', $3, 0.99, 1, NOW())
        RETURNING id;
      `, [offerId, quotationDoc.id, fragment]);

      const evId = evInsert.rows[0].id;
      createdEvidences.push({
        evidenceId: evId,
        requirementId: req.id,
        documentId: quotationDoc.id,
        fragment,
        page: 1
      });
    }

    return {
      offerId,
      supplierId,
      quotationDocId: quotationDoc.id,
      mandatoryReqs,
      createdEvidences,
      dbClient,
      cleanup: async () => {
        try {
          // CORRECCIÓN 2: Preservación del resultado terminal
          // Dejar intacta la cadena terminal del expediente (APPROVED) dentro del entorno de pruebas
          // hasta el teardown aislado del pipeline. No destruir selecciones finales, intentos,
          // workflows ni evaluaciones.
        } finally {
          await dbClient.end();
        }
      }
    };
  } catch (err) {
    await dbClient.end();
    throw err;
  }
}

test.describe('Document Intelligence E2E - Happy Path', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should complete the full happy path', async ({ page }) => {
    // Sanitizar logs de diagnóstico para no registrar tokens, cookies ni credenciales
    page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
    page.on('request', request => {
      if (request.url().includes('upload') || request.url().includes('documents')) {
        const sanitizedHeaders: Record<string, string> = {};
        for (const [k, v] of Object.entries(request.headers())) {
          if (k.toLowerCase() === 'authorization' || k.toLowerCase() === 'cookie') {
            sanitizedHeaders[k] = '[REDACTED]';
          } else {
            sanitizedHeaders[k] = v;
          }
        }
        console.log(`REQUEST: ${request.method()} ${request.url()} HEADERS: ${JSON.stringify(sanitizedHeaders)}`);
      }
    });
    test.setTimeout(120000);

    let preconditions: Awaited<ReturnType<typeof prepareHappyPathPreconditions>> | null = null;

    try {
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

      // Obtener el identificador real del expediente creado durante la propia prueba
      await page.waitForURL(/\/expedientes\/\d+/, { timeout: 15000 });
      const urlMatch = page.url().match(/\/expedientes\/(\d+)/);
      if (!urlMatch) {
        throw new Error(`Failed to extract caseId from URL: ${page.url()}`);
      }
      const currentCaseId = parseInt(urlMatch[1], 10);
      expect(currentCaseId).toBeGreaterThan(0);

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
      await expect(page.locator('button:has-text("Extraer requerimientos")').first()).toBeVisible({ timeout: 90000 });
      await page.click('button:has-text("Extraer requerimientos")');
      await expect(page.locator('text=Requerimientos extra').and(page.locator('text=dos/verificados')).first()).toBeVisible({ timeout: 30000 });

      // Review and confirm
      await page.click('button:has-text("Requerimiento")');
      await expect(page.locator('text=Revisi').and(page.locator('text=Pendiente')).first()).toBeVisible({ timeout: 15000 });
      const confirmButton = page.locator('button:has-text("Confirmar Revisi")').first();
      await expect(confirmButton).toBeVisible({ timeout: 15000 });
      await confirmButton.click();
      await expect(page.locator('text=Revisi').and(page.locator('text=Confirmada')).first()).toBeVisible({ timeout: 15000 });

      // 5. Vincular Proveedor (V6)
      await page.click('button:has-text("Proveedores")');
      await page.click('button:has-text("Vincular Proveedor")');
      await page.fill('input[name="ruc"]', '20123456789');
      await page.fill('input[name="business_name"]', 'Proveedor E2E');
      await page.click('button:has-text("Vincular")');
      await expect(page.locator('text=Proveedor E2E').first()).toBeVisible({ timeout: 15000 });

      // 6. Subir Cotización en Ofertas (V6) con compromisos técnicos verificables
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

      // 6.1 Precondición P12: Registrar evidencias vinculadas al documento real de cotización
      preconditions = await prepareHappyPathPreconditions(currentCaseId, 'mega_tenant');

      // 6.2 Vincular y verificar documentalmente las evidencias mediante endpoints P12 autorizados
      const token = await page.evaluate(() => localStorage.getItem('access_token'));
      expect(token).toBeTruthy();

      const linkedEvidenceIds: number[] = [];
      for (const ev of preconditions.createdEvidences) {
        // 6.2.1 Vincular evidencia a requisito vía POST /api/v6/cases/{id}/offers/{offer_id}/requirements/{req_id}/evidence
        const linkRes = await page.request.post(
          `/api/v6/cases/${currentCaseId}/offers/${preconditions.offerId}/requirements/${ev.requirementId}/evidence`,
          {
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            data: {
              offer_evidence_id: ev.evidenceId,
              document_id: ev.documentId,
              page: ev.page,
              fragment: ev.fragment,
              notes: 'Vinculación documental para acreditación de requisito'
            }
          }
        );
        expect(linkRes.ok()).toBeTruthy();
        const linkData = await linkRes.json();
        expect(linkData.document_id).toBe(ev.documentId);
        expect(linkData.offer_evidence_id).toBe(ev.evidenceId);
        expect(linkData.supplier_offer_id).toBe(preconditions.offerId);
        expect(linkData.requirement_id).toBe(ev.requirementId);
        expect(linkData.case_id).toBe(currentCaseId);
        expect(linkData.verification_status).toBe('PENDING');

        // 6.2.2 Verificar documentalmente la asociación vía PUT /api/v6/cases/{id}/evidence/{evidence_link_id}/review
        const reviewRes = await page.request.put(
          `/api/v6/cases/${currentCaseId}/evidence/${linkData.id}/review`,
          {
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            data: {
              verification_status: 'VERIFIED',
              notes: 'Verificación documental conforme por auditor técnico'
            }
          }
        );
        expect(reviewRes.ok()).toBeTruthy();
        const reviewData = await reviewRes.json();
        expect(reviewData.verification_status).toBe('VERIFIED');
        expect(reviewData.verified_by).not.toBeNull();
        linkedEvidenceIds.push(linkData.id);
      }

      // 7. Evaluar Oferta (V6)
      await page.click('button:has-text("Evaluaci")');
      await page.click('button:has-text("Evaluar Oferta")');
      await expect(page.locator('text=Resultados de Requisitos').first()).toBeVisible({ timeout: 60000 });

      // 7.1 Bloqueo Negativo P12: Comprobar que requisitos en REQUIERE_REVISION bloquean elegibilidad VfM y selección
      const evalsNegRes = await page.request.get(`/api/v6/cases/${currentCaseId}/evaluations`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      expect(evalsNegRes.ok()).toBeTruthy();
      const initialEvals = await evalsNegRes.json();
      expect(initialEvals.length).toBeGreaterThan(0);
      for (const ev of initialEvals) {
        expect(['REQUIERE_REVISION', 'MISSING_DATA']).toContain(ev.status);
      }

      // Consultar VFM y comprobar is_eligible = false
      const vfmNegRes = await page.request.get(`/api/v6/cases/${currentCaseId}/evaluations/vfm`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      expect(vfmNegRes.ok()).toBeTruthy();
      const vfmNegData = await vfmNegRes.json();
      const offerVfmNeg = vfmNegData.find((v: any) => v.supplier_offer_id === preconditions.offerId);
      expect(offerVfmNeg).toBeDefined();
      expect(offerVfmNeg.is_eligible).toBe(false);

      // Intentar selección por API y comprobar HTTP 400
      const blockedSelectRes = await page.request.post(`/api/v6/cases/${currentCaseId}/selection`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        data: {
          supplier_offer_id: preconditions.offerId,
          justification_comment: 'Intento de propuesta no elegible'
        }
      });
      expect(blockedSelectRes.status()).toBe(400);

      // Confirmar en DB ausencia de SupplierSelectionAttempt y SupplierSelectionFinal
      const selAttemptCheck = await preconditions.dbClient.query(
        'SELECT id FROM supplier_selection_attempts WHERE case_id = $1;',
        [currentCaseId]
      );
      expect(selAttemptCheck.rows.length).toBe(0);

      const selFinalCheck = await preconditions.dbClient.query(
        'SELECT id FROM supplier_selection_final WHERE case_id = $1;',
        [currentCaseId]
      );
      expect(selFinalCheck.rows.length).toBe(0);

      // Confirmar que el workflow no pasó a UNDER_REVIEW
      const caseStatusCheck = await preconditions.dbClient.query(
        'SELECT status FROM case_files WHERE id = $1;',
        [currentCaseId]
      );
      expect(caseStatusCheck.rows[0]?.status).not.toBe('UNDER_REVIEW');

      // 7.2 Revisión Técnica Humana Fundamentada por Requisito vía PUT /api/v6/cases/{case_id}/evaluations/{eval_id}
      // Resolver mediante PASSED única y exclusivamente aquellos requisitos que cuenten con acreditación técnica individual y motivada
      for (const ev of initialEvals) {
        const reqObj = preconditions.mandatoryReqs.find((r: any) => r.id === ev.requirement_id);
        if (!reqObj) {
          throw new Error(`Evaluación ${ev.id} corresponde a un requisito no identificado en la matriz.`);
        }

        // Localizar la evidencia documental verificada para este requisito específico
        const matchedEv = preconditions.createdEvidences.find((e: any) => e.requirementId === ev.requirement_id);
        if (!matchedEv) {
          // Si no existe evidencia pertinente para el requisito, fallar explícitamente el test y no forzar PASSED
          throw new Error(
            `No existe acreditación técnica documental para el requisito obligatorio '${reqObj.description}' (id: ${ev.requirement_id}). No se puede aprobar.`
          );
        }

        // Fundamentación individual y concreta por requisito, vinculada a la evidencia documental verídica
        let motivation = '';
        const descLower = (reqObj.description || '').toLowerCase();
        if (descLower.includes('computadoras') || descLower.includes('bienes')) {
          motivation = `Acreditación técnica individual para ${reqObj.description}: la cotización comercial ID ${matchedEv.documentId} (pág. ${matchedEv.page}) acredita de forma expresa el fragmento "${matchedEv.fragment}", cumpliendo íntegramente las especificaciones de computadoras de escritorio modelo corporativo.`;
        } else if (descLower.includes('cantidad') || descLower.includes('10')) {
          motivation = `Acreditación cuantitativa individual para ${reqObj.description}: la cotización comercial ID ${matchedEv.documentId} (pág. ${matchedEv.page}) acredita de forma expresa el fragmento "${matchedEv.fragment}", dando cumplimiento íntegro a la entrega de 10 unidades requeridas.`;
        } else {
          motivation = `Acreditación técnica individual para ${reqObj.description}: sustentada con evidencia documental verificada ID ${matchedEv.evidenceId} del documento fuente ID ${matchedEv.documentId}: "${matchedEv.fragment}".`;
        }

        const humanReviewRes = await page.request.put(
          `/api/v6/cases/${currentCaseId}/evaluations/${ev.id}`,
          {
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            data: {
              status: 'PASSED',
              explanation: motivation
            }
          }
        );
        expect(humanReviewRes.ok()).toBeTruthy();
        const updatedEv = await humanReviewRes.json();
        expect(updatedEv.status).toBe('PASSED');
        expect(updatedEv.validated_by).not.toBeNull();
        expect(updatedEv.validated_at).not.toBeNull();

        // Validar evento UPDATE_EVALUATION persistido en audit_logs
        const auditCheck = await preconditions.dbClient.query(
          `SELECT id, action, entity_type, entity_id, status
           FROM audit_logs
           WHERE entity_type = 'OfferEvaluation' AND entity_id = $1 AND action = 'UPDATE_EVALUATION'
           ORDER BY id DESC LIMIT 1;`,
          [String(ev.id)]
        );
        expect(auditCheck.rows.length).toBe(1);
        expect(auditCheck.rows[0]?.status).toBe('SUCCESS');
      }

      // 7.3 Probar Elegibilidad VfM tras resolución humana
      const evalsAfterRes = await page.request.get(`/api/v6/cases/${currentCaseId}/evaluations`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      expect(evalsAfterRes.ok()).toBeTruthy();
      const resolvedEvals = await evalsAfterRes.json();
      expect(resolvedEvals.length).toBeGreaterThanOrEqual(preconditions.mandatoryReqs.length);
      for (const ev of resolvedEvals) {
        expect(ev.status).toBe('PASSED');
        expect(['FAILED', 'CONFLICT', 'MISSING_DATA', 'REQUIERE_REVISION']).not.toContain(ev.status);
      }

      const vfmPostRes = await page.request.get(`/api/v6/cases/${currentCaseId}/evaluations/vfm`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      expect(vfmPostRes.ok()).toBeTruthy();
      const vfmPostData = await vfmPostRes.json();
      const offerVfmPost = vfmPostData.find((v: any) => v.supplier_offer_id === preconditions.offerId);
      expect(offerVfmPost).toBeDefined();
      expect(offerVfmPost.is_eligible).toBe(true);
      expect(offerVfmPost.total_score).toBeGreaterThan(0);

      // 8. Proponer Selección (V6) vía interfaz real
      await page.click('button:has-text("Selecci")');
      const proposeButton = page.locator('button:has-text("Proponer Selecci")').first();
      await expect(proposeButton).toBeEnabled({ timeout: 15000 });
      await proposeButton.click();
      await expect(page.locator('text=Propuesta de Selección Registrada').first()).toBeVisible({ timeout: 15000 });

      // Comprobar estado UNDER_REVIEW en el workflow institucional y en el intento de selección
      const attemptCheck = await preconditions.dbClient.query(
        'SELECT id, status, supplier_offer_id FROM supplier_selection_attempts WHERE case_id = $1 ORDER BY id DESC LIMIT 1;',
        [currentCaseId]
      );
      expect(attemptCheck.rows.length).toBe(1);
      expect(attemptCheck.rows[0]?.status).toBe('UNDER_REVIEW');
      expect(attemptCheck.rows[0]?.supplier_offer_id).toBe(preconditions.offerId);

      const workflowCheck = await preconditions.dbClient.query(
        'SELECT status FROM case_workflows WHERE case_id = $1;',
        [currentCaseId]
      );
      expect(workflowCheck.rows.length).toBe(1);
      expect(workflowCheck.rows[0]?.status).toBe('UNDER_REVIEW');

      // 9. Aprobación Interna Institucional (V6)
      await page.click('button:has-text("Resultado")');
      await page.click('button:has-text("Aprobar Propuesta de Selección")');
      await expect(page.locator('text=Selección Aprobada Internamente').first()).toBeVisible({ timeout: 15000 });

      // Comprobar resultado terminal y registros de auditoría
      const caseApproved = await preconditions.dbClient.query(
        'SELECT status FROM case_files WHERE id = $1;',
        [currentCaseId]
      );
      expect(caseApproved.rows[0]?.status).toBe('APPROVED');

      const finalSelection = await preconditions.dbClient.query(
        `SELECT ssf.id, ssf.case_id, ssa.supplier_offer_id
         FROM supplier_selection_final ssf
         JOIN supplier_selection_attempts ssa ON ssa.id = ssf.attempt_id
         WHERE ssf.case_id = $1;`,
        [currentCaseId]
      );
      expect(finalSelection.rows.length).toBe(1);
      expect(finalSelection.rows[0]?.supplier_offer_id).toBe(preconditions.offerId);

      const approvalAudit = await preconditions.dbClient.query(
        `SELECT id, action, entity_type FROM audit_logs
         WHERE entity_type = 'CaseFile' AND entity_id = $1 AND action = 'APPROVE_SELECTION' AND status = 'SUCCESS';`,
        [String(currentCaseId)]
      );
      expect(approvalAudit.rows.length).toBeGreaterThanOrEqual(1);
    } finally {
      if (preconditions) {
        await preconditions.cleanup();
      }
    }
  });

  test('guard: rechaza preparación cuando el expediente o tenant no coinciden o host no autorizado', async () => {
    // 1. Expediente inexistente
    await expect(prepareHappyPathPreconditions(-99999, 'mega_tenant')).rejects.toThrow(
      /Security guard failed/
    );

    // 2. Tenant ajeno o incorrecto
    await expect(prepareHappyPathPreconditions(1, 'unauthorized_foreign_tenant')).rejects.toThrow(
      /Security guard failed/
    );

    // 3. Host arbitrario no autorizado
    await expect(prepareHappyPathPreconditions(1, 'mega_tenant', 'postgresql://test_user:test_password@evil-host.com:5432/test_db')).rejects.toThrow(
      /Unauthorized host/
    );

    // 4. Verificación negativa adicional: cuando no existe fragmento documental pertinente, la prueba debe rechazar la preparación sin crear acreditación positiva
    const connStr = process.env.DATABASE_URL || 'postgresql://test_user:test_password@db-test:5432/test_db';
    const testDb = new Client({ connectionString: connStr });
    await testDb.connect();
    try {
      // Crear caso sintético temporal
      const tempCase = await testDb.query(`
        INSERT INTO case_files (tenant_id, title, status, contract_type, created_at)
        VALUES ('mega_tenant', 'Guard Test Case', 'WAITING_QUOTATION', 'bienes', NOW())
        RETURNING id;
      `);
      const tempCaseId = tempCase.rows[0].id;

      // Obtener o crear proveedor de prueba
      let supplierId: number;
      const supRes = await testDb.query(
        "SELECT id FROM suppliers WHERE tenant_id = 'mega_tenant' LIMIT 1;"
      );
      if (supRes.rows.length > 0) {
        supplierId = supRes.rows[0].id;
      } else {
        const newSup = await testDb.query(`
          INSERT INTO suppliers (tenant_id, legal_name, tax_id, created_at)
          VALUES ('mega_tenant', 'Proveedor Guard SAC', '20999888772', NOW())
          RETURNING id;
        `);
        supplierId = newSup.rows[0].id;
      }

      // Crear oferta para el caso
      const offRes = await testDb.query(`
        INSERT INTO supplier_offers (case_id, supplier_id, status, evaluation_status, currency, created_at)
        VALUES ($1, $2, 'RECEIVED', 'UNDER_REVIEW', 'PEN', NOW())
        RETURNING id;
      `, [tempCaseId, supplierId]);
      const tempOfferId = offRes.rows[0].id;

      // Subir documento de cotización sintético
      await testDb.query(`
        INSERT INTO uploaded_documents (case_id, original_filename, document_type, stored_path, mime_type, processing_status, created_at)
        VALUES ($1, 'quot.pdf', 'oferta', '/app/uploads/guard_quot.pdf', 'application/pdf', 'COMPLETED', NOW());
      `, [tempCaseId]);

      // Insertar requisito obligatorio sin respaldo en la cotización
      const dummyReq = await testDb.query(`
        INSERT INTO case_requirement_matrices (case_id, requirement_type, description, mandatory, status, flows_to_contract, created_at)
        VALUES ($1, 'TECHNICAL', 'Requisito No Contenido: Suministro de 500 Vehiculos Blindados', true, 'REVIEW_REQUIRED', false, NOW())
        RETURNING id;
      `, [tempCaseId]);
      const dummyReqId = dummyReq.rows[0].id;

      try {
        await expect(prepareHappyPathPreconditions(tempCaseId, 'mega_tenant')).rejects.toThrow(
          /No documentary evidence corresponding to mandatory requirement/
        );

        // Confirmar que no se creó ninguna evidencia positiva ni vinculación para este requisito sin sustento
        const evCheck = await testDb.query(
          'SELECT id FROM offer_requirement_evidences WHERE requirement_id = $1;',
          [dummyReqId]
        );
        expect(evCheck.rows.length).toBe(0);

        const offEvCheck = await testDb.query(
          'SELECT id FROM offer_evidences WHERE supplier_offer_id = $1;',
          [tempOfferId]
        );
        expect(offEvCheck.rows.length).toBe(0);
      } finally {
        await testDb.query('DELETE FROM case_requirement_matrices WHERE case_id = $1;', [tempCaseId]);
        await testDb.query('DELETE FROM uploaded_documents WHERE case_id = $1;', [tempCaseId]);
        await testDb.query('DELETE FROM supplier_offers WHERE id = $1;', [tempOfferId]);
        await testDb.query('DELETE FROM case_files WHERE id = $1;', [tempCaseId]);
      }
    } finally {
      await testDb.end();
    }
  });
});
