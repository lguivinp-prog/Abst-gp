// Normalizes visual state
export const getSourceVisualState = (validation: any) => {
  if (!validation) return 'UNAVAILABLE';

  const s = validation.status;
  const source = validation.source?.toUpperCase() || '';

  if (s === 'PASSED' || s === 'VALIDATED' || s === 'VALIDADO' || s === 'SUCCESS') return 'VERIFIED';

  // FUP has MANUAL_REQUIRED because it's failing
  if (source === 'FUP' && (s === 'MANUAL_REQUIRED' || s === 'UNAVAILABLE' || s === 'NO_DISPONIBLE_API')) return 'UNAVAILABLE';

  if (s === 'REVIEW_REQUIRED' || s === 'MANUAL_REQUIRED' || s === 'OBSERVED') return 'REVIEW';
  if (s === 'NOT_AVAILABLE' || s === 'UNAVAILABLE' || s === 'NOT_CONFIGURED' || s === 'NO_DISPONIBLE_API') return 'UNAVAILABLE';
  if (s === 'PENDING') return 'PENDING';
  if (s === 'FAILED' || s === 'ERROR' || s === 'BLOCKED') return 'ERROR';

  return 'UNAVAILABLE';
};

// Gets the latest automatic validation per source
export const getLatestAutomaticValidation = (validations: any[], source: string) => {
  if (!validations) return null;
  const filtered = validations.filter(v => v.source?.toUpperCase() === source.toUpperCase() && v.validation_mode !== 'MANUAL');
  if (filtered.length === 0) return null;
  // sort by requested_at descending
  return filtered.sort((a, b) => new Date(b.requested_at || 0).getTime() - new Date(a.requested_at || 0).getTime())[0];
};

export const getSupplierValidationSummary = (validations: any[]) => {
  const sources = ['SUNAT', 'MIGO_ACTIVITIES', 'CIIU', 'RNP', 'FUP'];
  const latestVals = sources.map(s => getLatestAutomaticValidation(validations, s)).filter(Boolean);

  // Extract specific flags
  let supplierNeedsReview = false;
  let supplierHasAlert = false;

  // Check for cross_source_consistency false or REVIEW_REQUIRED in ANY payload
  for (const val of latestVals) {
    const payload = val.response_payload || {};
    if (payload.cross_source_consistency === false || payload.cross_source_status === 'REVIEW_REQUIRED' || payload.cross_source_reason === 'ACTIVITY_SOURCE_MISMATCH') {
      supplierNeedsReview = true;
      supplierHasAlert = true;
    }
  }

  // Calculate global status
  const states = latestVals.map(getSourceVisualState);

  // The supplier needs review if any status is REVIEW, or if the transversal flag is set.
  if (states.includes('REVIEW')) supplierNeedsReview = true;

  let globalStatus = 'VALIDATED';
  let globalLabel = 'Validaciones completadas';
  let globalVariant = 'success';

  if (states.includes('ERROR')) {
    globalStatus = 'ERROR';
    globalLabel = 'Error de consulta';
    globalVariant = 'danger';
  } else if (supplierNeedsReview) {
    globalStatus = 'REVIEW';
    globalLabel = 'Requiere revisión';
    globalVariant = 'warning';
  } else if (states.includes('UNAVAILABLE')) {
    globalStatus = 'INCOMPLETE';
    globalLabel = 'Información parcial';
    globalVariant = 'warning';
  } else if (states.includes('PENDING')) {
    globalStatus = 'PENDING';
    globalLabel = 'Pendiente';
    globalVariant = 'secondary';
  } else if (states.length === 0) {
    globalStatus = 'NO_DATA';
    globalLabel = 'Sin Datos';
    globalVariant = 'secondary';
  }

  return {
    status: globalStatus,
    label: globalLabel,
    variant: globalVariant,
    supplierNeedsReview,
    supplierHasAlert,
    latestVals
  };
};
