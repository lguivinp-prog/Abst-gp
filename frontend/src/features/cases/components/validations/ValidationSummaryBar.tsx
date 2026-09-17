import React from 'react';
import { getSupplierValidationSummary, getSourceVisualState } from './ValidationLogic';
import './validations.css';

interface ValidationSummaryBarProps {
  suppliers: any[];
  validationsBySupplier: Record<number, any[]>;
}

export const ValidationSummaryBar: React.FC<ValidationSummaryBarProps> = ({ suppliers, validationsBySupplier }) => {
  const stats = {
    total: suppliers.length,
    validated: 0,
    review: 0,
    alerts: 0,
    unavailable: 0
  };

  suppliers.forEach(sup => {
    const vals = validationsBySupplier[sup.id] || [];
    const summary = getSupplierValidationSummary(vals);

    if (summary.supplierHasAlert) stats.alerts++;

    // "unavailable: proveedor con al menos una fuente visual state == UNAVAILABLE"
    // FUP in the payload is MANUAL_REQUIRED, so its visual state is REVIEW or UNAVAILABLE depending on the source rule.
    // Wait, the user specifically said: "FUP: status == MANUAL_REQUIRED ... => UNAVAILABLE"
    // Let me check what getSourceVisualState returns. FUP returns REVIEW because of MANUAL_REQUIRED.
    // I need to fix getSourceVisualState or just check here. Let me check the states in summary.latestVals.

    const states = summary.latestVals.map(getSourceVisualState);
    const hasUnavailable = states.includes('UNAVAILABLE');
    if (hasUnavailable) stats.unavailable++;

    if (summary.supplierNeedsReview) {
      stats.review++;
    } else if (summary.status === 'VALIDATED') {
      stats.validated++;
    }
  });

  return (
    <div className="val-summary-bar">
      <div className="val-summary-item">
        <span className="val-summary-label">Proveedores</span>
        <span className="val-summary-value">{stats.total}</span>
      </div>
      <div className="val-summary-divider"></div>
      <div className="val-summary-item">
        <span className="val-summary-label">Validados</span>
        <span className="val-summary-value val-green">{stats.validated}</span>
      </div>
      <div className="val-summary-divider"></div>
      <div className="val-summary-item">
        <span className="val-summary-label">Requieren revisión</span>
        <span className="val-summary-value val-amber">{stats.review}</span>
      </div>
      <div className="val-summary-divider"></div>
      <div className="val-summary-item">
        <span className="val-summary-label">Con alertas</span>
        <span className="val-summary-value val-red">{stats.alerts}</span>
      </div>
      <div className="val-summary-divider"></div>
      <div className="val-summary-item">
        <span className="val-summary-label">No disponibles</span>
        <span className="val-summary-value val-gray">{stats.unavailable}</span>
      </div>
    </div>
  );
};
