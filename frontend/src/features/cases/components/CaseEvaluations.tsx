import React, { useState, useEffect } from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Clock, RefreshCw, BarChart2 } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { evaluationService } from '../../../api/v6/evaluation.service';
import type { EvaluationResponse } from '../../../api/v6/evaluation.types';
import { offerService } from '../../../api/v6/offer.service';
import type { SupplierOfferResponse } from '../../../api/v6/offer.types';
import { AppError } from '../../../api/apiError';
import './CaseEvaluations.css';

interface CaseEvaluationsProps {
  caseId: string;
}

export const CaseEvaluations: React.FC<CaseEvaluationsProps> = ({ caseId }) => {
  const [evaluations, setEvaluations] = useState<EvaluationResponse[]>([]);
  const [offers, setOffers] = useState<SupplierOfferResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<number | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [evalsData, offersData] = await Promise.all([
        evaluationService.getCaseEvaluations(caseId),
        offerService.getOffers(caseId)
      ]);
      setEvaluations(evalsData);
      setOffers(offersData);
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error inesperado al cargar las evaluaciones.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [caseId]);

  const handleEvaluateOffer = async (offerId: number) => {
    setIsEvaluating(offerId);
    setError(null);
    try {
      await evaluationService.evaluateOffer(caseId, offerId);
      await loadData();
    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Error al evaluar la oferta.');
      }
    } finally {
      setIsEvaluating(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PASSED': 
      case 'IMPROVEMENT': return <Badge variant="success"><CheckCircle2 size={14} className="mr-1" /> Cumple</Badge>;
      case 'CONFLICT': return <Badge variant="danger"><XCircle size={14} className="mr-1" /> Conflicto</Badge>;
      case 'MISSING_DATA': return <Badge variant="warning"><AlertTriangle size={14} className="mr-1" /> Incompleto</Badge>;
      default: return <Badge variant="secondary"><Clock size={14} className="mr-1" /> {status}</Badge>;
    }
  };

  if (loading && offers.length === 0) {
    return (
      <div className="case-evaluations-loading">
        <div className="spinner"></div>
        <p>Cargando evaluaciones...</p>
      </div>
    );
  }

  return (
    <div className="case-evaluations-container">
      <div className="case-evaluations-header">
        <div>
          <h2>Evaluación Técnica y Documental</h2>
          <p>Evalúe las ofertas completadas contra los requisitos del expediente.</p>
        </div>
        <Button variant="outline" onClick={loadData}>
          <RefreshCw size={16} className="mr-2" />
          Actualizar
        </Button>
      </div>

      {error && <div className="case-evaluations-error"><AlertTriangle size={16} /> {error}</div>}

      {offers.length === 0 ? (
        <div className="case-evaluations-empty">
          <BarChart2 size={48} className="empty-icon" />
          <h3>No hay ofertas para evaluar</h3>
          <p>Aún no se han recibido ofertas o vinculado proveedores a este expediente.</p>
        </div>
      ) : (
        <div className="case-evaluations-list">
          {offers.map(offer => {
            const offerEvals = evaluations.filter(e => e.supplier_offer_id === offer.id);
            const isEvaluated = offerEvals.length > 0;
            const isIncomplete = offer.status === 'PENDING' && !offer.price && !offer.source_document;

            return (
              <div key={offer.id} className="evaluation-card">
                <div className="evaluation-header">
                  <div className="offer-info">
                    <h4>{offer.supplier?.business_name || `Proveedor #${offer.supplier_id}`}</h4>
                    <span className="offer-price">
                      {offer.price !== undefined && offer.price !== null ? `Precio: $${offer.price}` : 'Sin oferta económica'}
                    </span>
                  </div>
                  <div className="evaluation-actions">
                    {isIncomplete ? (
                      <span className="incomplete-text">Oferta incompleta</span>
                    ) : (
                      <Button 
                        onClick={() => handleEvaluateOffer(offer.id)}
                        disabled={isEvaluating === offer.id}
                        variant={isEvaluated ? "outline" : "primary"}
                      >
                        {isEvaluating === offer.id ? 'Evaluando...' : isEvaluated ? 'Re-evaluar Oferta' : 'Evaluar Oferta'}
                      </Button>
                    )}
                  </div>
                </div>

                {isEvaluated && (
                  <div className="evaluation-results">
                    <h5>Resultados de Requisitos</h5>
                    <div className="results-grid">
                      {offerEvals.map(evalItem => (
                        <div key={evalItem.id} className="result-item">
                          <div className="result-status">
                            {getStatusBadge(evalItem.status)}
                          </div>
                          <div className="result-details">
                            <span className="req-id">
                              <Badge variant="secondary" className="mr-2">
                                {evalItem.requirement_type || 'Requisito'} #{evalItem.requirement_id}
                              </Badge>
                            </span>
                            <span className="req-description">
                              <strong>{evalItem.requirement_description || 'Sin descripción'}</strong>
                            </span>
                            <span className="explanation">{evalItem.explanation || 'Sin observaciones'}</span>
                            {evalItem.evaluation_confidence !== undefined && (
                              <span className="confidence mt-1 text-xs text-gray-500">
                                Confianza: {(evalItem.evaluation_confidence * 100).toFixed(1)}%
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
