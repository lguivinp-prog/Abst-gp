import React, { useState, useEffect } from 'react';
import { Button } from '../../../components/ui/Button';
import { casesService } from '../../../api/cases.service';
import { Flag } from 'lucide-react';
import './CaseEvaluations.css'; // Reusing css for layout

interface CaseResultProps {
  caseId: string;
}

export const CaseResult: React.FC<CaseResultProps> = ({ caseId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [selection, setSelection] = useState<any | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
    setSubmitting(true);
    setError(null);
    try {
      await casesService.approveSelection(caseId);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Error al aprobar selección (¿tiene rol de Supervisor?)');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div>Cargando resultado...</div>;

  return (
    <div className="v6-evaluations-container">
      <div className="v6-evaluations-header">
        <h2 className="v6-evaluations-title">Resultado del Expediente</h2>
        <p className="v6-evaluations-subtitle">Decisión final y adjudicación del expediente.</p>
      </div>

      {error && <div className="text-red-600 mb-4">{error}</div>}

      {result ? (
        <div className="mb-6 p-6 border rounded bg-green-50 border-green-200 shadow-sm">
          <h3 className="font-bold flex items-center gap-2 text-green-800 text-lg mb-4">
            <Flag size={20} className="text-green-600"/> 
            Expediente Adjudicado
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-gray-500 mb-1">Proveedor Adjudicado</p>
              <p className="font-medium">{result.supplier_name || 'Desconocido'} (RUC: {result.supplier_ruc || 'N/A'})</p>
            </div>
            <div>
              <p className="text-gray-500 mb-1">Importe de Adjudicación</p>
              <p className="font-medium text-lg text-green-700">
                {result.offer_currency} {result.offer_price != null ? result.offer_price.toLocaleString('es-PE', {minimumFractionDigits: 2}) : 'N/A'}
              </p>
            </div>
            <div>
              <p className="text-gray-500 mb-1">Justificación</p>
              <p>{result.justification_comment || 'Ninguna proporcionada'}</p>
            </div>
            <div>
              <p className="text-gray-500 mb-1">Fecha de Adjudicación</p>
              <p>{result.created_at && !isNaN(new Date(result.created_at).getTime()) ? new Date(result.created_at).toLocaleString('es-PE') : 'Fecha no disponible'}</p>
            </div>
          </div>
        </div>
      ) : selection && selection.status === 'UNDER_REVIEW' ? (
        <div className="mb-6 p-4 border rounded bg-yellow-50 border-yellow-200">
          <h3 className="font-bold mb-2">Selección Propuesta (En Revisión)</h3>
          <p>Hay una propuesta pendiente de revisión por el supervisor.</p>
          <p><strong>Comentario de justificación:</strong> {selection.justification_comment || 'Ninguno'}</p>
          <Button 
            onClick={handleApprove} 
            disabled={submitting}
            variant="primary"
            className="mt-4"
          >
            Aprobar y Adjudicar
          </Button>
        </div>
      ) : (
        <div className="p-4 border rounded bg-gray-50">
          <p>No hay resultado definido ni selección pendiente.</p>
        </div>
      )}
    </div>
  );
};
