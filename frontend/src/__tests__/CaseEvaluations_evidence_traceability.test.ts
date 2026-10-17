import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RequirementEvidenceResponse, RequirementEvidenceReview } from '../api/v6/evaluation.types';

/**
 * Pure state reducer simulating the evidence traceability review logic in CaseEvaluations
 */
interface EvidenceReviewState {
  verificationStatus: 'PENDING' | 'VERIFIED' | 'REJECTED' | 'OBSERVED';
  verifiedBy?: string;
  verifiedAt?: string;
  notes?: string;
}

function resolveRequirementStatus(evidences: EvidenceReviewState[]): string {
  if (evidences.length === 0) {
    return 'MISSING_DATA';
  }
  if (evidences.some(e => e.verificationStatus === 'REJECTED')) {
    return 'FAILED';
  }
  if (evidences.some(e => e.verificationStatus === 'PENDING' || e.verificationStatus === 'OBSERVED')) {
    return 'REQUIERE_REVISION';
  }
  if (evidences.every(e => e.verificationStatus === 'VERIFIED')) {
    return 'PASSED';
  }
  return 'REQUIERE_REVISION';
}

function updateEvidenceReview(
  evidence: RequirementEvidenceResponse,
  review: RequirementEvidenceReview,
  username: string
): RequirementEvidenceResponse {
  return {
    ...evidence,
    verification_status: review.verification_status,
    verified_by_username: username,
    verified_at: new Date().toISOString(),
    notes: review.notes
  };
}

test('Sin evidencia vinculada se resuelve estrictamente como MISSING_DATA', () => {
  const status = resolveRequirementStatus([]);
  assert.equal(status, 'MISSING_DATA');
});

test('Evidencia en PENDING o OBSERVED resuelve como REQUIERE_REVISION', () => {
  const pendingStatus = resolveRequirementStatus([
    { verificationStatus: 'PENDING' }
  ]);
  assert.equal(pendingStatus, 'REQUIERE_REVISION');

  const observedStatus = resolveRequirementStatus([
    { verificationStatus: 'OBSERVED', notes: 'Requiere aclaración técnica' }
  ]);
  assert.equal(observedStatus, 'REQUIERE_REVISION');
});

test('Evidencia con estatus REJECTED resuelve como FAILED independientemente de otras', () => {
  const status = resolveRequirementStatus([
    { verificationStatus: 'VERIFIED' },
    { verificationStatus: 'REJECTED', notes: 'Garantía insuficiente' }
  ]);
  assert.equal(status, 'FAILED');
});

test('Todas las evidencias VERIFIED resuelven como PASSED', () => {
  const status = resolveRequirementStatus([
    { verificationStatus: 'VERIFIED', verifiedBy: 'supervisor_1' },
    { verificationStatus: 'VERIFIED', verifiedBy: 'operator_1' }
  ]);
  assert.equal(status, 'PASSED');
});

test('updateEvidenceReview actualiza correctamente el estado, usuario y fecha', () => {
  const initial: RequirementEvidenceResponse = {
    id: 101,
    case_id: 1,
    supplier_offer_id: 5,
    requirement_id: 12,
    offer_evidence_id: 20,
    source_document: 'propuesta.pdf',
    page: 4,
    fragment: 'Garantía 24 meses',
    verification_status: 'PENDING'
  };

  const updated = updateEvidenceReview(
    initial,
    { verification_status: 'VERIFIED', notes: 'Validado con ficha técnica' },
    'supervisor_user'
  );

  assert.equal(updated.verification_status, 'VERIFIED');
  assert.equal(updated.verified_by_username, 'supervisor_user');
  assert.equal(updated.notes, 'Validado con ficha técnica');
  assert.ok(updated.verified_at);
});
