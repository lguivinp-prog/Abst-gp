import React, { useState, useEffect } from 'react';
import { Shield, ShieldAlert, ShieldCheck, Clock, AlertCircle, RefreshCw, Building2 } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { validationService } from '../../../api/v6/validation.service';
import type { ValidationRequestResponse } from '../../../api/v6/validation.types';
import { supplierService } from '../../../api/v6/supplier.service';
import type { CaseSupplierResponse } from '../../../api/v6/supplier.types';
import { AppError } from '../../../api/apiError';
import './CaseValidations.css';

interface CaseValidationsProps {
  caseId: string;
}

export const CaseValidations: React.FC<CaseValidationsProps> = ({ caseId }) => {
  const [validations, setValidations] = useState<ValidationRequestResponse[]>([]);
  const [suppliers, setSuppliers] = useState<CaseSupplierResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [selectedSupplierId, setSelectedSupplierId] = useState<number | ''>('');
  const [selectedSource, setSelectedSource] = useState<string>('SUNAT');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [valsData, supsData] = await Promise.all([
        validationService.getValidations(caseId),
        supplierService.getCaseSuppliers(caseId)
      ]);
      setValidations(valsData);
      setSuppliers(supsData);
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error inesperado al cargar las validaciones.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [caseId]);

  const handleRequestValidation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSupplierId) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await validationService.createValidation(caseId, selectedSupplierId as number, { source: selectedSource });
      setShowForm(false);
      setSelectedSupplierId('');
      await loadData();
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error al solicitar la validación.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

    const getStatusBadge = (status: string) => {
      switch (status) {
        case 'PASSED':
        case 'VERIFIED': return <Badge variant="success"><ShieldCheck size={14} className="mr-1" /> VALIDADO</Badge>;
        case 'WARNING': return <Badge variant="warning"><ShieldAlert size={14} className="mr-1" /> OBSERVADO</Badge>;
        case 'MANUAL_REQUIRED':
        case 'NO_DISPONIBLE_API': return <Badge variant="warning"><ShieldAlert size={14} className="mr-1" /> NO DISPONIBLE</Badge>;
        case 'BLOCKED':
        case 'ERROR': return <Badge variant="danger"><ShieldAlert size={14} className="mr-1" /> ERROR</Badge>;
        case 'RUNNING': return <Badge variant="primary"><RefreshCw size={14} className="mr-1 spin" /> EN PROCESO</Badge>;
        default: return <Badge variant="secondary"><Clock size={14} className="mr-1" /> PENDIENTE</Badge>;
      }
    };

  if (loading && validations.length === 0) {
    return (
      <div className="case-validations-loading">
        <div className="spinner"></div>
        <p>Cargando validaciones...</p>
      </div>
    );
  }

  return (
    <div className="case-validations-container">
      <div className="case-validations-header">
        <div>
          <h2>Validaciones Externas</h2>
          <p>Solicite y consulte integraciones externas (SUNAT, RNP, FUP) para los proveedores de este expediente.</p>
        </div>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancelar' : 'Nueva Validación'}
        </Button>
      </div>

      {error && <div className="case-validations-error"><AlertCircle size={16} /> {error}</div>}

      {showForm && (
        <form className="case-validations-form" onSubmit={handleRequestValidation}>
          <h3>Solicitar Validación</h3>
          <div className="form-group">
            <label>Proveedor</label>
            <select
              value={selectedSupplierId}
              onChange={e => setSelectedSupplierId(e.target.value ? Number(e.target.value) : '')}
              required
            >
              <option value="">Seleccione un proveedor</option>
              {suppliers.map(sup => (
                <option key={sup.id} value={sup.id}>{sup.business_name} (RUC: {sup.ruc})</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>Fuente (Integración)</label>
            <select value={selectedSource} onChange={e => setSelectedSource(e.target.value)} required>
              <option value="ALL">Validar Todo (Orquestador)</option>
              <option value="SUNAT">SUNAT</option>
              <option value="RNP">RNP</option>
              <option value="FUP">FUP</option>
              <option value="CIIU">CIIU</option>
            </select>
          </div>
          <div className="form-actions">
            <Button type="submit" disabled={isSubmitting || !selectedSupplierId}>
              {isSubmitting ? 'Solicitando...' : 'Solicitar'}
            </Button>
          </div>
        </form>
      )}

      {validations.length === 0 && !showForm && (
        <div className="case-validations-empty">
          <Shield size={48} className="empty-icon" />
          <h3>No hay validaciones</h3>
          <p>Aún no se han solicitado validaciones para los proveedores de este expediente.</p>
        </div>
      )}

      {validations.length > 0 && (
        <div className="case-validations-list">
          {validations.map(val => (
            <div key={val.id} className="case-validation-card">
              <div className="validation-header">
                <div className="validation-supplier">
                  <Building2 size={18} />
                  <h4>{val.supplier?.business_name || `Proveedor #${val.supplier_id}`}</h4>
                  {val.supplier?.ruc && <span className="supplier-ruc">RUC: {val.supplier.ruc}</span>}
                </div>
                <div className="validation-status">
                  {getStatusBadge(val.status)}
                </div>
              </div>

              <div className="validation-body">
                <div className="validation-details">
                  <div className="detail-item">
                    <span className="label">Fuente:</span>
                    <span className="value fw-bold">{val.source}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Solicitado el:</span>
                    <span className="value">{new Date(val.requested_at).toLocaleString()}</span>
                  </div>
                  <div className="detail-item">
                    <span className="label">Completado el:</span>
                    <span className="value">{val.completed_at ? new Date(val.completed_at).toLocaleString() : '-'}</span>
                  </div>
                </div>
                {val.response_payload && (
                  <div className="validation-payload">
                    <span className="label">Respuesta:</span>
                    <pre>{JSON.stringify(val.response_payload, null, 2)}</pre>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
