import { Building2, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import { getSupplierValidationSummary, getSourceVisualState } from './ValidationLogic';
import { SupplierValidationTabs } from './SupplierValidationTabs';

interface SupplierValidationCardProps {
  supplier: any;
  validations: any[];
  isExpanded: boolean;
  onToggle: () => void;
  onCiiuDetail: (ciiuData: any) => void;
}

export const SupplierValidationCard: React.FC<SupplierValidationCardProps> = ({
  supplier,
  validations,
  isExpanded,
  onToggle,
  onCiiuDetail
}) => {
  // Get main statuses
  const getMiniBadge = (val: any, label: string, extra?: string) => {
    const state = getSourceVisualState(val);

    if (state === 'VERIFIED') {
      return <span className="val-badge val-success">✓ {label}{extra ? ` ${extra}` : ''}</span>;
    }
    if (state === 'UNAVAILABLE') {
      if (label === 'FUP') {
        return <span className="val-badge" style={{ backgroundColor: '#f3f4f6', color: '#6b7280', border: '1px solid #e5e7eb' }}>– {label}</span>;
      }
      return <span className="val-badge val-secondary">{label} -</span>;
    }
    if (state === 'ERROR') {
      return <span className="val-badge val-danger">✗ {label}</span>;
    }
    if (state === 'REVIEW') {
      return <span className="val-badge val-warning">! {label}{extra ? ` ${extra}` : ''}</span>;
    }

    return <span className="val-badge val-secondary">• {label}</span>;
  };

  const summary = getSupplierValidationSummary(validations);

  // Extract specific validations mapped from the summary
  const sunatVal = summary.latestVals.find(v => v.source?.toUpperCase() === 'SUNAT');
  const migoVal = summary.latestVals.find(v => v.source?.toUpperCase() === 'MIGO_ACTIVITIES');
  const ciiuVal = summary.latestVals.find(v => v.source?.toUpperCase() === 'CIIU');
  const rnpVal = summary.latestVals.find(v => v.source?.toUpperCase() === 'RNP');
  const fupVal = summary.latestVals.find(v => v.source?.toUpperCase() === 'FUP');

  const maxDate = summary.latestVals.length > 0
    ? new Date(Math.max(...summary.latestVals.filter(v => v.requested_at).map(v => new Date(v.requested_at).getTime())))
    : null;

  return (
    <div className={`val-card ${summary.supplierHasAlert && !isExpanded ? 'border-l-4 border-l-amber-400' : ''}`} style={summary.supplierHasAlert && !isExpanded ? { borderLeft: '4px solid #f59e0b' } : {}}>
      {/* Header / Collapsed View */}
      <div className="val-card-header" onClick={onToggle} style={{ cursor: 'pointer' }}>
        <div style={{ flex: 1 }}>
          <div className="val-card-title-group" style={{ justifyContent: 'space-between' }}>
            <div className="val-card-title-group">
              <Building2 size={20} color="#6b7280" />
              <h3 className="val-card-title">
                {supplier.business_name || `Proveedor #${supplier.id}`}
              </h3>
              {summary.supplierNeedsReview ? (
                <span className="val-badge val-warning">REQUIERE REVISIÓN</span>
              ) : (
                <span className={`val-badge val-${summary.variant}`}>
                  {summary.status === 'VALIDATED' ? 'VALIDADO' : summary.status === 'INCOMPLETE' ? 'INCOMPLETO' : summary.label.toUpperCase()}
                </span>
              )}
            </div>
            <div className="val-card-actions" style={{ gap: '16px' }}>
              {maxDate && <span className="val-card-meta">{maxDate.toLocaleString()}</span>}
              <button className="val-toggle-btn">
                {isExpanded ? 'Ocultar detalle' : 'Ver detalle'}
                {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </button>
            </div>
          </div>

          <div className="val-card-meta" style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '24px' }}>
            <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>RUC {supplier.ruc}</span>
            <div className="val-card-badges" style={{ marginBottom: 0 }}>
              {getMiniBadge(sunatVal, 'SUNAT')}
              {getMiniBadge(migoVal, 'ACTIVIDADES', migoVal?.response_payload?.activities ? `(${migoVal.response_payload.activities.length})` : '')}
              {getMiniBadge(ciiuVal, 'CIIU')}
              {getMiniBadge(rnpVal, 'RNP')}
              {getMiniBadge(fupVal, 'FUP')}
            </div>
          </div>
        </div>
      </div>

      {/* Alerta visible incluso colapsado si hay mismatch */}
      {summary.supplierHasAlert && !isExpanded && (
        <div className="val-card-alert">
          <AlertTriangle size={16} />
          Diferencia entre fuentes consultadas
        </div>
      )}

      {/* Expanded Details / Tabs */}
      {isExpanded && (
        <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: '16px' }}>
          <SupplierValidationTabs
            supplier={supplier}
            validations={validations}
            onCiiuDetail={onCiiuDetail}
          />
        </div>
      )}
    </div>
  );
};
