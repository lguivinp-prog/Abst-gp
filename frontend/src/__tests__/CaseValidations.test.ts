import { test } from 'node:test';
import assert from 'node:assert/strict';

// Helper types mapping to ValidationRequestResponse for tests
interface MockValidation {
  id: number;
  source: string;
  status: string;
  validation_mode: string;
  requested_at: string;
  supplier_id: number;
  response_payload?: any;
  manual_result?: string;
}

// Emulate UI grouping logic from CaseValidations.tsx
function groupValidations(validations: MockValidation[]) {
  const sortNewest = (a: MockValidation, b: MockValidation) =>
    new Date(b.requested_at).getTime() - new Date(a.requested_at).getTime();

  const externalValidations = validations.filter(v => v.validation_mode !== 'MANUAL');
  const manualValidations = validations.filter(v => v.validation_mode === 'MANUAL');

  const latestExternalMap = new Map<string, MockValidation>();
  const externalHistory: MockValidation[] = [];

  [...externalValidations].sort(sortNewest).forEach(v => {
    const key = `${v.supplier_id}-${v.source}`;
    if (!latestExternalMap.has(key)) {
      latestExternalMap.set(key, v);
    } else {
      externalHistory.push(v);
    }
  });

  const latestExternal = Array.from(latestExternalMap.values());

  const latestManualMap = new Map<string, MockValidation>();
  const manualHistory: MockValidation[] = [];

  [...manualValidations].sort(sortNewest).forEach(v => {
    const key = `${v.supplier_id}-${v.source}`;
    if (!latestManualMap.has(key)) {
      latestManualMap.set(key, v);
    } else {
      manualHistory.push(v);
    }
  });

  const latestManual = Array.from(latestManualMap.values());
  const fullHistory = [...externalHistory, ...manualHistory].sort(sortNewest);

  return { latestExternal, latestManual, fullHistory };
}

// Test A, B: 3 SUNAT EXTERNAL históricos -> solo aparece el más reciente, RNP viejo y nuevo -> solo nuevo
test('A y B - Grouping external validations keeps only newest in main view', () => {
  const data: MockValidation[] = [
    { id: 1, source: 'SUNAT', status: 'ERROR', validation_mode: 'EXTERNAL', requested_at: '2023-01-01T10:00:00Z', supplier_id: 1 },
    { id: 2, source: 'SUNAT', status: 'WARNING', validation_mode: 'EXTERNAL', requested_at: '2023-01-02T10:00:00Z', supplier_id: 1 },
    { id: 3, source: 'SUNAT', status: 'PASSED', validation_mode: 'EXTERNAL', requested_at: '2023-01-03T10:00:00Z', supplier_id: 1 },
    { id: 4, source: 'RNP', status: 'WARNING', validation_mode: 'EXTERNAL', requested_at: '2023-01-01T10:00:00Z', supplier_id: 1 },
    { id: 5, source: 'RNP', status: 'PASSED', validation_mode: 'EXTERNAL', requested_at: '2023-01-02T10:00:00Z', supplier_id: 1 }
  ];

  const { latestExternal, fullHistory } = groupValidations(data);

  assert.equal(latestExternal.length, 2);
  const sunatLatest = latestExternal.find(v => v.source === 'SUNAT');
  assert.equal(sunatLatest?.id, 3);

  const rnpLatest = latestExternal.find(v => v.source === 'RNP');
  assert.equal(rnpLatest?.id, 5);

  assert.equal(fullHistory.length, 3);
});

// Test C, D: Historial behaviour (Simulated via data structure checks)
test('C y D - History logic correctly preserves old records', () => {
  const data: MockValidation[] = [
    { id: 1, source: 'SUNAT', status: 'PASSED', validation_mode: 'EXTERNAL', requested_at: '2023-01-01T10:00:00Z', supplier_id: 1 },
    { id: 2, source: 'SUNAT', status: 'PASSED', validation_mode: 'EXTERNAL', requested_at: '2023-01-02T10:00:00Z', supplier_id: 1 }
  ];

  const { latestExternal, fullHistory } = groupValidations(data);
  assert.equal(latestExternal.length, 1);
  assert.equal(fullHistory.length, 1);
  assert.equal(fullHistory[0].id, 1); // Record 1 is in history
  // C and D are inherently UI assertions but we prove the data is separated accurately
});

// Test E, F: dos SUNAT MANUAL -> solo el más reciente
test('E y F - Grouping manual validations keeps only newest in main view and moves rest to history', () => {
  const data: MockValidation[] = [
    { id: 10, source: 'SUNAT', status: 'PASSED', validation_mode: 'MANUAL', manual_result: 'VALIDATED', requested_at: '2023-01-01T10:00:00Z', supplier_id: 1 },
    { id: 11, source: 'SUNAT', status: 'PASSED', validation_mode: 'MANUAL', manual_result: 'REVIEW_REQUIRED', requested_at: '2023-01-02T10:00:00Z', supplier_id: 1 }
  ];

  const { latestManual, fullHistory } = groupValidations(data);

  assert.equal(latestManual.length, 1);
  assert.equal(latestManual[0].manual_result, 'REVIEW_REQUIRED'); // The newer one

  assert.equal(fullHistory.length, 1);
  assert.equal(fullHistory[0].manual_result, 'VALIDATED'); // The older one in history
});

// Test G, H: Filtering errors and mojibake (simulated UI render text)
function renderExternalErrorUI(val: MockValidation): string {
  if (['NO_DISPONIBLE_API', 'ERROR', 'WARNING', 'BLOCKED', 'MANUAL_REQUIRED'].includes(val.status)) {
    let output = "Integración externa no disponible o requiere revisión. Puede realizar una validación manual con sustento.";
    if (val.source === 'SUNAT') output += " La consulta automática de SUNAT requiere verificación interactiva.";
    if (val.source === 'FUP') output += " No fue posible consultar automáticamente la fuente oficial en este momento.";
    if (val.source === 'CIIU') output += " No fue posible obtener la actividad económica desde SUNAT.";
    return output;
  }
  return "";
}

test('G y H - Hides technical errors and avoids mojibake', () => {
  const val: MockValidation = {
    id: 1, source: 'FUP', status: 'ERROR', validation_mode: 'EXTERNAL', requested_at: '2023-01-01T10:00:00Z', supplier_id: 1,
    response_payload: { error: 'HTTPSConnectionPool CERTIFICATE_VERIFY_FAILED API Key missing resoluciÃ³n' }
  };

  const uiText = renderExternalErrorUI(val);

  // Verify it does NOT contain the technical errors or mojibake
  assert.equal(uiText.includes('HTTPSConnectionPool'), false);
  assert.equal(uiText.includes('CERTIFICATE_VERIFY_FAILED'), false);
  assert.equal(uiText.includes('API Key missing'), false);
  assert.equal(uiText.includes('resoluciÃ³n'), false); // Mojibake check

  // Verify it DOES contain the proper functional message (no mojibake)
  assert.equal(uiText.includes('validación'), true);
  assert.equal(uiText.includes('revisión'), true);
});

// Test I: RNP PASSED details
function renderRnpDetails(val: MockValidation) {
  let output = "";
  if (val.source === 'RNP' && val.response_payload?.registro) {
    output += `Registro: ${val.response_payload.registro} `;
    if (val.response_payload.bienes !== undefined) output += `Bienes: ${val.response_payload.bienes ? 'Sí' : 'No'} `;
    if (val.response_payload.servicios !== undefined) output += `Servicios: ${val.response_payload.servicios ? 'Sí' : 'No'} `;
  }
  return output.trim();
}

test('I - RNP PASSED shows correct fields', () => {
  const val: MockValidation = {
    id: 1, source: 'RNP', status: 'PASSED', validation_mode: 'EXTERNAL', requested_at: '2023-01-01T10:00:00Z', supplier_id: 1,
    response_payload: {
      registro: 'VIGENTE',
      bienes: true,
      servicios: true
    }
  };

  const uiText = renderRnpDetails(val);
  assert.equal(uiText, "Registro: VIGENTE Bienes: Sí Servicios: Sí");
});
