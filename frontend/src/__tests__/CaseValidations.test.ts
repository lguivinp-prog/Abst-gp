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
