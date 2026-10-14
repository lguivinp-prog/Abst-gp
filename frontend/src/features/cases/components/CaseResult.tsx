import React, { useState, useEffect } from 'react';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { casesService } from '../../../api/cases.service';
import { useAuth } from '../../auth/AuthContext';
import { CheckCircle2, Clock, ShieldCheck, AlertCircle, Info } from 'lucide-react';
import './CaseEvaluations.css';

interface CaseResultProps {
  caseId: string;
}

export const CaseResult: React.FC<CaseResultProps> = ({ caseId }) => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [selection, setSelection] = useState<any | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Control RBAC en la UI (Etapa 4): Solo Supervisores o Administradores pueden aprobar
  const canApprove = user?.role === 'SUPERVISOR' || user?.role === 'ADMIN';

  useEffect(() => {
    loadData();
  }, [caseId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [resData, selData] = await Promise.all([
        casesService.getResult(caseId).catch(() => null),
        casesService.getSelection(caseId).catch(() => null)
      ]);
      setResult(resData);
      setSelection(selData);
    } catch (err: any) {
      setError(err.message || 'Error al cargar resultado');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!canApprove) {
      setError('Solo usuarios con rol de Supervisor o Administrador están autorizados para aprobar propuestas de selección.');
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await casesService.approveSelection(caseId);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Error al aprobar la propuesta de selección');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="case-evaluations-loading">
        <div className="spinner"></div>
        <p>Cargando resultado del expediente...</p>
      </div>
    );
  }

  return (
    <div className="v6-evaluations-container">
      <div className="v6-evaluations-header">
        <div>
          <h2 className="v6-evaluations-title">Aprobación Interna y Resultado</h2>
          <p className="v6-evaluations-subtitle">
            Validación administrativa interna de la propuesta de selección para la continuidad del expediente.
          </p>
        </div>
      </div>

      {error && (
        <div className="case-evaluations-error mb-4 flex items-center gap-2">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* CASO 1: SELECCIÓN APROBADA INTERNAMENTE */}
      {result ? (
        <div className="mb-6 p-6 border rounded-lg bg-emerald-50 border-emerald-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold flex items-center gap-2 text-emerald-900 text-lg">
              <CheckCircle2 size={22} className="text-emerald-600" />
              Selección Aprobada Internamente
            </h3>
            <Badge variant="success" className="px-3 py-1 text-xs">
              Aprobada Internamente
            </Badge>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm bg-white p-4 rounded border border-emerald-100">
            <div>
              <p className="text-gray-500 mb-0.5 text-xs">Proveedor Propuesto / Seleccionado</p>
              <p className="font-semibold text-gray-900">
                {result.supplier_name || 'Desconocido'}
              </p>
              <p className="text-xs text-gray-500">RUC: {result.supplier_ruc || 'N/A'}</p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5 text-xs">Importe de la Oferta Seleccionada</p>
              <p className="font-bold text-lg text-emerald-700">
                {result.offer_currency || 'PEN'}{' '}
                {result.offer_total_amount != null
                  ? Number(result.offer_total_amount).toLocaleString('es-PE', { minimumFractionDigits: 2 })
                  : 'N/A'}
              </p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5 text-xs">Justificación de la Selección</p>
              <p className="text-gray-800 text-xs leading-relaxed">
                {result.justification_comment || 'Coincidente con la mejor recomendación determinista del sistema.'}
              </p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5 text-xs">Fecha de Aprobación Interna</p>
              <p className="text-gray-800 font-medium">
                {result.created_at && !isNaN(new Date(result.created_at).getTime())
                  ? new Date(result.created_at).toLocaleString('es-PE')
                  : 'Fecha no disponible'}
              </p>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-emerald-200 flex items-start gap-2 text-xs text-emerald-800">
            <Info size={15} className="text-emerald-600 flex-shrink-0 mt-0.5" />
            <p>
              <strong>Aviso de alcance legal:</strong> La aprobación registrada en el sistema certifica la conformidad técnica y procedimental de la propuesta en el expediente. No constituye otorgamiento de buena pro, adjudicación oficial ni perfeccionamiento del contrato frente a proveedores.
            </p>
          </div>
        </div>
      ) : selection && selection.status === 'UNDER_REVIEW' ? (
        /* CASO 2: PROPUESTA DE SELECCIÓN PENDIENTE DE REVISIÓN */
        <div className="mb-6 p-6 border rounded-lg bg-amber-50 border-amber-200 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold flex items-center gap-2 text-amber-900 text-base">
              <Clock size={20} className="text-amber-600" />
              Propuesta de Selección Pendiente de Revisión
            </h3>
            <Badge variant="warning" className="px-2.5 py-0.5 text-xs">
              En Revisión
            </Badge>
          </div>

          <p className="text-xs text-amber-800 mb-4">
            Existe una propuesta de selección registrada en el expediente pendiente de validación por la supervisión autorizada.
          </p>

          <div className="bg-white p-4 rounded border border-amber-100 text-xs space-y-2 mb-4">
            <p>
              <strong>Oferta Propuesta:</strong> #{selection.supplier_offer_id}
            </p>
            <p>
              <strong>Justificación presentada:</strong>{' '}
              {selection.justification_comment || 'Selección coincidente con la mejor recomendación técnica del sistema.'}
            </p>
          </div>

          {canApprove ? (
            <div className="pt-2">
              <Button
                onClick={handleApprove}
                disabled={submitting}
                variant="primary"
                className="flex items-center gap-2"
              >
                <ShieldCheck size={16} />
                {submitting ? 'Aprobando...' : 'Aprobar Propuesta de Selección'}
              </Button>
              <p className="text-[11px] text-gray-500 mt-2">
                Al aprobar, el expediente pasará al estado de aprobación interna (APPROVED) y quedará protegido contra modificaciones.
              </p>
            </div>
          ) : (
            <div className="p-3 bg-gray-100 border border-gray-200 rounded text-xs text-gray-600 flex items-center gap-2">
              <Info size={16} className="text-gray-500" />
              <span>
                Acción de aprobación restringida: Solo usuarios con rol de <strong>Supervisor</strong> o <strong>Administrador</strong> pueden validar y aprobar la propuesta de selección. Su usuario actual cuenta con rol de Operador.
              </span>
            </div>
          )}
        </div>
      ) : (
        /* CASO 3: SIN PROPUESTA NI RESULTADO */
        <div className="p-6 border rounded-lg bg-gray-50 text-center text-gray-500 text-sm">
          <p className="mb-1 font-medium text-gray-700">No hay selección propuesta ni resultado final registrado.</p>
          <p className="text-xs text-gray-500">
            Primero debe formular una propuesta en la pestaña <strong>Selección</strong> a partir de las ofertas evaluadas.
          </p>
        </div>
      )}
    </div>
  );
};
