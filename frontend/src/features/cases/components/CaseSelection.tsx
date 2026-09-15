import React, { useState, useEffect } from 'react';
import { Button } from '../../../components/ui/Button';
import { casesService } from '../../../api/cases.service';
import { Trophy } from 'lucide-react';
import './CaseEvaluations.css'; // Reusing css

interface CaseSelectionProps {
  caseId: string;
}

export const CaseSelection: React.FC<CaseSelectionProps> = ({ caseId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<any | null>(null);
  const [offers, setOffers] = useState<any[]>([]);
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadData();
  }, [caseId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [selRes, offRes] = await Promise.all([
        casesService.getSelection(caseId).catch(() => null),
        casesService.getOffers(caseId)
      ]);
      setSelection(selRes);
      setOffers(Array.isArray(offRes) ? offRes : []);
    } catch (err: any) {
      setError(err.message || 'Error al cargar selección');
    } finally {
      setLoading(false);
    }
  };

  const handlePropose = async (offerId: number) => {
    setSubmitting(true);
    setError(null);
    try {
      await casesService.proposeSelection(caseId, {
        supplier_offer_id: offerId,
        justification_comment: justification
      });
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Error al proponer selección');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div>Cargando candidatos...</div>;

  return (
    <div className="v6-evaluations-container">
      <div className="v6-evaluations-header">
        <h2 className="v6-evaluations-title">Selección de Proveedor</h2>
        <p className="v6-evaluations-subtitle">Propuesta de ganador basada en las ofertas recibidas y evaluadas.</p>
      </div>

      {error && <div className="text-red-600 mb-4">{error}</div>}

      {selection && (
        <div className="mb-6 p-4 border rounded bg-blue-50 border-blue-200">
          <h3 className="font-bold flex items-center gap-2"><Trophy size={18}/> Selección Propuesta</h3>
          <p><strong>Estado:</strong> {selection.status}</p>
          <p><strong>Comentario:</strong> {selection.justification_comment || 'Ninguno'}</p>
        </div>
      )}

      <div className="v6-eval-list">
        {offers.length === 0 ? (
          <p>No hay ofertas registradas.</p>
        ) : (
          offers.map(offer => (
            <div key={offer.id} className="v6-eval-card p-4 border rounded mb-4">
              <h3 className="font-bold">Proveedor ID: {offer.supplier_id}</h3>
              <p>Precio: {offer.price || 'No definido'}</p>
              <p>Estado de Oferta: {offer.status}</p>
              
              {!selection && (
                <div className="mt-4">
                  <input
                    type="text"
                    placeholder="Justificación (opcional)"
                    value={justification}
                    onChange={(e) => setJustification(e.target.value)}
                    className="border p-2 mr-2 w-full mb-2 rounded"
                    disabled={submitting}
                  />
                  <Button 
                    onClick={() => handlePropose(offer.id)} 
                    disabled={submitting}
                    variant="primary"
                  >
                    Proponer Selección
                  </Button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
