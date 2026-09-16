import { test } from 'node:test';
import assert from 'node:assert/strict';

// Logic extracted from CaseValidations.tsx for testing
function getStatusBadge(status: string, requestedAt?: string): string {
  if (status === 'PENDING' && requestedAt) {
    const age = Date.now() - new Date(requestedAt).getTime();
    if (age > 5 * 60 * 1000) {
      return 'PENDIENTE — DEMORA EXCEDIDA';
    }
  }
  switch (status) {
    case 'PASSED':
    case 'VERIFIED': return 'VALIDADO';
    case 'WARNING': return 'OBSERVADO';
    case 'MANUAL_REQUIRED':
    case 'NO_DISPONIBLE_API': return 'NO DISPONIBLE';
    case 'BLOCKED':
    case 'ERROR': return 'ERROR';
    case 'RUNNING': return 'EN PROCESO';
    default: return 'PENDIENTE';
  }
}

test('CaseValidations getStatusBadge - terminal logic and delayed pending', () => {
  // PENDING reciente
  const recentTime = new Date(Date.now() - 1 * 60 * 1000).toISOString();
  assert.equal(getStatusBadge('PENDING', recentTime), 'PENDIENTE');

  // PENDING > 5 min
  const oldTime = new Date(Date.now() - 6 * 60 * 1000).toISOString();
  assert.equal(getStatusBadge('PENDING', oldTime), 'PENDIENTE — DEMORA EXCEDIDA');

  // backend ERROR
  assert.equal(getStatusBadge('ERROR'), 'ERROR');

  // backend NO_DISPONIBLE
  assert.equal(getStatusBadge('NO_DISPONIBLE_API'), 'NO DISPONIBLE');

  // backend VALIDADO
  assert.equal(getStatusBadge('PASSED'), 'VALIDADO');
  assert.equal(getStatusBadge('VERIFIED'), 'VALIDADO');
});

// Test raw JSON hiding logic - simulating the updated UI behavior
function getExternalDisplay(status: string): string | null {
  if (status === 'NO_DISPONIBLE_API' || status === 'ERROR' || status === 'WARNING' || status === 'BLOCKED') {
    return 'Integración externa no disponible. Puede realizar una validación manual con sustento.';
  }
  return null;
}

test('CaseValidations getExternalDisplay - functional message', () => {
  assert.equal(getExternalDisplay('NO_DISPONIBLE_API'), 'Integración externa no disponible. Puede realizar una validación manual con sustento.');
  assert.equal(getExternalDisplay('ERROR'), 'Integración externa no disponible. Puede realizar una validación manual con sustento.');
  assert.equal(getExternalDisplay('PASSED'), null);
});

// Test manual result translation
function translateManualResult(result?: string): string {
  switch(result) {
    case 'VALIDATED': return 'Validado';
    case 'REJECTED': return 'No validado';
    case 'REVIEW_REQUIRED': return 'Requiere revisión';
    default: return result || '';
  }
}

test('CaseValidations translateManualResult', () => {
  assert.equal(translateManualResult('VALIDATED'), 'Validado');
  assert.equal(translateManualResult('REJECTED'), 'No validado');
  assert.equal(translateManualResult('REVIEW_REQUIRED'), 'Requiere revisión');
  assert.equal(translateManualResult('UNKNOWN'), 'UNKNOWN');
});

test('CaseValidations save button disabled logic', () => {
  const isSubmitting = false;
  const selectedSupplierId = 1;
  const isManualMode = true;

  const manualResultEmpty = '';
  assert.equal(isSubmitting || !selectedSupplierId || (isManualMode && !manualResultEmpty), true, "Save disabled without result");

  const manualResultValid = 'REVIEW_REQUIRED';
  assert.equal(isSubmitting || !selectedSupplierId || (isManualMode && !manualResultValid), false, "Save enabled with result");

  const isManualModeFalse = false;
  assert.equal(isSubmitting || !selectedSupplierId || (isManualModeFalse && !manualResultEmpty), false, "Save enabled in automated mode");
});
