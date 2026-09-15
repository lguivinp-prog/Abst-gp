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
        <div className="mb-6 p-6 border rounded bg-green-50 border-green-200">
          <h3 className="font-bold flex items-center gap-2 text-green-800 text-lg mb-2"><Flag size={20}/> Adjudicado</h3>
          <p><strong>ID de Intento:</strong> {result.attempt_id}</p>
          <p><strong>Fecha:</strong> {new Date(result.created_at).toLocaleString()}</p>
          <p><strong>Estado:</strong> Aprobado Definitivo</p>
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
