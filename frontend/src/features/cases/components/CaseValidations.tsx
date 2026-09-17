import React, { useState, useEffect } from 'react';
import { Shield, ShieldAlert, ShieldCheck, Clock, AlertCircle, RefreshCw, Building2, CheckSquare, ChevronDown, ChevronRight } from 'lucide-react';
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
  const [isManualMode, setIsManualMode] = useState(false);
  const [selectedSupplierId, setSelectedSupplierId] = useState<number | ''>('');
  const [selectedSource, setSelectedSource] = useState<string>('SUNAT');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [manualResult, setManualResult] = useState<'' | 'VALIDATED' | 'REJECTED' | 'REVIEW_REQUIRED'>('');
  const [manualObservation, setManualObservation] = useState('');
  const [manualEvidence, setManualEvidence] = useState('');

  const [showHistory, setShowHistory] = useState(false);

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
    if (isManualMode && !manualResult) {
      setError("Debe seleccionar un resultado manual.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      if (isManualMode) {
        await validationService.createManualValidation(caseId, selectedSupplierId as number, {
          source: selectedSource === 'ALL' ? 'SUNAT' : selectedSource,
          result: manualResult as any,
          observation: manualObservation,
          evidence_reference: manualEvidence
        });
      } else {
        await validationService.createValidation(caseId, selectedSupplierId as number, { source: selectedSource });
      }
      setShowForm(false);
      setSelectedSupplierId('');
      setManualObservation('');
      setManualEvidence('');
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

  const getStatusBadge = (status: string, requestedAt?: string) => {
    if (status === 'PENDING' && requestedAt) {
      const age = Date.now() - new Date(requestedAt).getTime();
      if (age > 5 * 60 * 1000) {
        return <Badge variant="warning"><Clock size={14} className="mr-1" /> PENDIENTE — DEMORA EXCEDIDA</Badge>;
      }
    }
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

  const translateManualResult = (result?: string) => {
    switch(result) {
      case 'VALIDATED': return 'Validado';
      case 'REJECTED': return 'No validado';
      case 'REVIEW_REQUIRED': return 'Requiere revisión';
      default: return result || '';
    }
  };

  const sortNewest = (a: ValidationRequestResponse, b: ValidationRequestResponse) =>
    new Date(b.requested_at).getTime() - new Date(a.requested_at).getTime();

  // Logic for grouping
  const externalValidations = validations.filter(v => v.validation_mode !== 'MANUAL');
  const manualValidations = validations.filter(v => v.validation_mode === 'MANUAL');

  const latestExternalMap = new Map<string, ValidationRequestResponse>();
  const externalHistory: ValidationRequestResponse[] = [];

  [...externalValidations].sort(sortNewest).forEach(v => {
    const key = `${v.supplier_id}-${v.source}`;
    if (!latestExternalMap.has(key)) {
      latestExternalMap.set(key, v);
    } else {
      externalHistory.push(v);
    }
  });

  const latestExternal = Array.from(latestExternalMap.values());
  const maxExternalDate = latestExternal.length > 0
    ? new Date(Math.max(...latestExternal.map(v => new Date(v.requested_at).getTime())))
    : null;

  const latestManualMap = new Map<string, ValidationRequestResponse>();
  const manualHistory: ValidationRequestResponse[] = [];

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

  if (loading && validations.length === 0) {
    return (
      <div className="case-validations-loading">
        <div className="spinner"></div>
        <p>Cargando validaciones...</p>
      </div>
    );
  }

  const renderValidationCard = (val: ValidationRequestResponse, isHistory: boolean = false) => (
    <div key={val.id} className="case-validation-card">
      <div className="validation-header">
        <div className="validation-supplier">
          <Building2 size={18} />
          <h4>{val.supplier?.business_name || `Proveedor #${val.supplier_id}`}</h4>
          {val.supplier?.ruc && <span className="supplier-ruc">RUC: {val.supplier.ruc}</span>}
        </div>
        <div className="validation-status">
          {val.validation_mode === 'MANUAL' && <Badge variant="primary" className="mr-2"><CheckSquare size={14} className="mr-1" /> MANUAL</Badge>}
          {getStatusBadge(val.status, val.requested_at)}
        </div>
      </div>

      <div className="validation-body">
        <div className="validation-details">
          <div className="detail-item">
            <span className="label">Fuente{val.validation_mode === 'MANUAL' ? ' original' : ''}:</span>
            <span className="value fw-bold">{val.source}</span>
          </div>
          <div className="detail-item">
            <span className="label">{val.validation_mode === 'MANUAL' ? 'Registrado el' : 'Solicitado el'}:</span>
            <span className="value">{new Date(val.requested_at).toLocaleString()}</span>
          </div>
          {!isHistory && val.validation_mode !== 'MANUAL' && (
            <div className="detail-item">
              <span className="label">Completado el:</span>
              <span className="value">{val.completed_at ? new Date(val.completed_at).toLocaleString() : '-'}</span>
            </div>
          )}
          {val.validation_mode === 'MANUAL' && val.verified_by_user_id && (
            <div className="detail-item">
              <span className="label">Verificado por:</span>
              <span className="value">{val.verified_by_user?.full_name || val.verified_by_user?.username || `Usuario #${val.verified_by_user_id}`}</span>
            </div>
          )}
        </div>

        {!isHistory && val.validation_mode === 'MANUAL' ? (
          <div className="validation-payload manual-payload">
            <p><strong>Resultado:</strong> {translateManualResult(val.manual_result)}</p>
            <p><strong>Observación:</strong> {val.manual_observation}</p>
            {val.manual_evidence_reference && <p><strong>Evidencia:</strong> {val.manual_evidence_reference}</p>}
          </div>
        ) : !isHistory && val.validation_mode !== 'MANUAL' ? (
          <>
            {(val.status === 'NO_DISPONIBLE_API' || val.status === 'ERROR' || val.status === 'WARNING' || val.status === 'BLOCKED' || val.status === 'MANUAL_REQUIRED') && (
              <div className="validation-payload">
                <p className="text-sm text-amber-700 m-0">Integración externa no disponible o requiere revisión. Puede realizar una validación manual con sustento.</p>
                {val.source === 'SUNAT' && <p className="text-sm font-medium text-amber-800 mt-1">La consulta automática de SUNAT requiere verificación interactiva.</p>}
                {val.source === 'FUP' && <p className="text-sm font-medium text-amber-800 mt-1">No fue posible consultar automáticamente la fuente oficial en este momento.</p>}
                {val.source === 'CIIU' && <p className="text-sm font-medium text-amber-800 mt-1">No fue posible obtener la actividad económica desde SUNAT.</p>}
              </div>
            )}
            {val.status === 'PASSED' && val.response_payload && (
              <div className="validation-payload">
                <details>
                  <summary className="text-sm cursor-pointer text-blue-600">Ver detalle</summary>
                  <div className="mt-2 text-sm bg-gray-50 p-2 rounded">
                    {val.source === 'SUNAT' && val.response_payload.estado && (
                      <>
                        <p><strong>Estado:</strong> {val.response_payload.estado}</p>
                        <p><strong>Condición:</strong> {val.response_payload.condicion}</p>
                      </>
                    )}
                    {val.source === 'RNP' && val.response_payload.registro && (
                      <>
                        <p><strong>Registro:</strong> {val.response_payload.registro}</p>
                        {val.response_payload.bienes !== undefined && <p><strong>Bienes:</strong> {val.response_payload.bienes ? 'Sí' : 'No'}</p>}
                        {val.response_payload.servicios !== undefined && <p><strong>Servicios:</strong> {val.response_payload.servicios ? 'Sí' : 'No'}</p>}
                        {val.response_payload.vigencia && val.response_payload.vigencia !== "Datos extraidos de html publico" && val.response_payload.vigencia !== "Datos extraídos de html público" && <p><strong>Vigencia:</strong> {val.response_payload.vigencia}</p>}
                      </>
                    )}
                    {val.source === 'CIIU' && val.response_payload.ciiu && (
                      <>
                        <p><strong>CIIU Extraído:</strong> {val.response_payload.ciiu.join(', ')}</p>
                      </>
                    )}
                  </div>
                </details>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );

  return (
    <div className="case-validations-container">
      <div className="case-validations-header">
        <div>
          <h2>Validaciones de Proveedores</h2>
          <p>Consulte integraciones externas o registre verificaciones manuales con sustento.</p>
        </div>
        <div className="case-validations-actions flex gap-2">
          <Button onClick={async () => {
            setIsSubmitting(true);
            try {
              for (const sup of suppliers) {
                await validationService.createValidation(caseId, sup.id, { source: 'ALL' });
              }
              await loadData();
            } catch (err) {
              if (err instanceof AppError) setError(err.message);
              else setError('Error al orquestar validaciones.');
            } finally {
              setIsSubmitting(false);
            }
          }} disabled={isSubmitting || suppliers.length === 0} className="bg-blue-600 hover:bg-blue-700 text-white">
            {isSubmitting ? 'Ejecutando...' : 'Ejecutar Validaciones Automáticas'}
          </Button>
          <Button variant="outline" onClick={() => {
            setShowForm(!showForm);
            setIsManualMode(true);
            if (selectedSource === 'ALL') setSelectedSource('SUNAT');
          }}>
            {showForm && isManualMode ? 'Cancelar' : 'Nueva Validación Manual'}
          </Button>
        </div>
      </div>

      {error && <div className="case-validations-error"><AlertCircle size={16} /> {error}</div>}

      {showForm && (
        <form className="case-validations-form" onSubmit={handleRequestValidation}>
          <h3>{isManualMode ? 'Registrar Validación Manual' : 'Solicitar Validación'}</h3>
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
              {!isManualMode && <option value="ALL">Validar Todo (Orquestador)</option>}
              <option value="SUNAT">SUNAT</option>
              <option value="RNP">RNP</option>
              <option value="FUP">FUP</option>
              <option value="CIIU">CIIU</option>
            </select>
          </div>

          {isManualMode && (
            <>
              <div className="form-group">
                <label>Resultado Manual</label>
                <select value={manualResult} onChange={e => setManualResult(e.target.value as any)} required>
                  <option value="">Seleccione un resultado</option>
                  <option value="VALIDATED">Validado</option>
                  <option value="REJECTED">No validado</option>
                  <option value="REVIEW_REQUIRED">Requiere revisión</option>
                </select>
              </div>
              <div className="form-group">
                <label>Observación</label>
                <textarea
                  value={manualObservation}
                  onChange={e => setManualObservation(e.target.value)}
                  required
                  placeholder="Detalle de la validación..."
                  rows={3}
                />
              </div>
              <div className="form-group">
                <label>Evidencia (Referencia)</label>
                <input
                  type="text"
                  value={manualEvidence}
                  onChange={e => setManualEvidence(e.target.value)}
                  placeholder="Ej. Constancia PDF adjunta"
                />
              </div>
            </>
          )}

          <div className="form-actions">
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancelar</Button>
            <Button type="submit" disabled={isSubmitting || !selectedSupplierId || (isManualMode && !manualResult)}>
              {isSubmitting ? 'Guardando...' : (isManualMode ? 'Guardar Validación' : 'Solicitar')}
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
          <div className="flex justify-between items-end border-b pb-2 mt-4 mb-3">
            <h3 className="section-title m-0 border-0 pb-0">VALIDACIONES AUTOMÁTICAS</h3>
            {maxExternalDate && (
              <span className="text-sm text-gray-500 font-medium">Última validación automática: {maxExternalDate.toLocaleString()}</span>
            )}
          </div>
          {latestExternal.length === 0 && (
            <p className="text-gray-500 italic text-sm mb-4">No hay validaciones automáticas registradas.</p>
          )}
          {latestExternal.map(val => renderValidationCard(val))}

          <h3 className="section-title mt-6 mb-3 border-b pb-2">VALIDACIONES MANUALES</h3>
          {latestManual.length === 0 && (
            <p className="text-gray-500 italic text-sm mb-4">No hay validaciones manuales registradas.</p>
          )}
          {latestManual.map(val => renderValidationCard(val))}

          {fullHistory.length > 0 && (
            <div className="mt-8 border rounded-lg overflow-hidden bg-white shadow-sm">
              <button
                className="w-full px-4 py-3 flex items-center justify-between text-gray-700 hover:bg-gray-50 transition-colors font-medium border-b"
                onClick={() => setShowHistory(!showHistory)}
              >
                <span>Ver historial de validaciones ({fullHistory.length})</span>
                {showHistory ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
              </button>

              {showHistory && (
                <div className="p-4 bg-gray-50">
                  {fullHistory.map(val => renderValidationCard(val, true))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
