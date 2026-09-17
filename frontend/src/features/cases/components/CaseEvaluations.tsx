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
  const [contractualEvals, setContractualEvals] = useState<any[]>([]);
  const [vfmRanking, setVfmRanking] = useState<any[]>([]);
  const [offers, setOffers] = useState<SupplierOfferResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<number | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [evalsData, offersData, contractualData, vfmData] = await Promise.all([
        evaluationService.getCaseEvaluations(caseId),
        offerService.getOffers(caseId),
        evaluationService.getContractualEvaluations(caseId),
        evaluationService.getVFMRanking(caseId)
      ]);
      setEvaluations(evalsData);
      setOffers(offersData);
      setContractualEvals(contractualData);
      setVfmRanking(vfmData);
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
      case 'CUMPLE':
      case 'IMPROVEMENT':
      case 'CUMPLE_Y_MEJORA': return <Badge variant="success"><CheckCircle2 size={14} className="mr-1" /> Cumple</Badge>;
      case 'CONFLICT':
      case 'NO_CUMPLE': return <Badge variant="danger"><XCircle size={14} className="mr-1" /> No Cumple</Badge>;
      case 'MISSING_DATA':
      case 'NO_OFERTADO': return <Badge variant="warning"><AlertTriangle size={14} className="mr-1" /> Incompleto</Badge>;
      case 'REQUIERE_REVISION': return <Badge variant="warning"><AlertTriangle size={14} className="mr-1" /> Revisa</Badge>;
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
        <>
          {vfmRanking && vfmRanking.length > 0 && (
            <div className="case-evaluations-list mb-8">
              <div className="evaluation-card bg-blue-50 border-blue-200">
                <div className="evaluation-header border-b border-blue-100 pb-4 mb-4">
                  <h3 className="text-lg font-semibold text-blue-900">Ranking Valor por Dinero (VFM)</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-blue-100 text-blue-900 border-b border-blue-200">
                      <tr>
                        <th className="p-3 font-semibold">Rank</th>
                        <th className="p-3 font-semibold">Proveedor</th>
                        <th className="p-3 font-semibold">Estado</th>
                        <th className="p-3 font-semibold text-right">Puntaje</th>
                        <th className="p-3 font-semibold text-right">Precio Total</th>
                        <th className="p-3 font-semibold text-right">Ratio (Precio/Pto)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-blue-100 bg-white">
                      {vfmRanking.map((vfm, idx) => {
                        const off = offers.find(o => o.id === vfm.supplier_offer_id);
                        const provName = off?.supplier?.business_name || `Proveedor #${vfm.supplier_id}`;
                        const currencyStr = off?.currency === 'USD' ? 'US$' : 'S/';

                        return (
                          <tr key={vfm.supplier_offer_id} className={!vfm.is_eligible ? "opacity-60 bg-gray-50" : ""}>
                            <td className="p-3 font-bold text-gray-500">
                              {vfm.is_eligible ? `#${idx + 1}` : '-'}
                            </td>
                            <td className="p-3 font-medium text-gray-900">{provName}</td>
                            <td className="p-3">
                              {vfm.is_eligible ? (
                                <Badge variant="success">Elegible</Badge>
                              ) : (
                                <Badge variant="danger">Descalificado</Badge>
                              )}
                            </td>
                            <td className="p-3 text-right">{vfm.is_eligible ? vfm.total_score : '-'}</td>
                            <td className="p-3 text-right">
                              {vfm.is_eligible ? `${currencyStr} ${vfm.price.toLocaleString('en-US', {minimumFractionDigits: 2})}` : '-'}
                            </td>
                            <td className="p-3 text-right font-semibold text-blue-700">
                              {vfm.is_eligible ? vfm.vfm_ratio.toFixed(2) : '-'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

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

                    <div className="mt-6 border-t pt-4">
                      <h5 className="mb-4">Matriz de Cumplimiento Contractual</h5>
                      {contractualEvals.filter(e => e.supplier_offer_id === offer.id).length === 0 ? (
                        <p className="text-sm text-gray-500 italic">No hay condiciones contractuales evaluadas para esta oferta.</p>
                      ) : (
                        <div className="overflow-x-auto border border-gray-200 rounded">
                          <table className="w-full text-sm text-left">
                            <thead className="bg-gray-50 border-b border-gray-200">
                              <tr>
                                <th className="p-2 font-medium">Condición</th>
                                <th className="p-2 font-medium">Requerido</th>
                                <th className="p-2 font-medium">Ofertado</th>
                                <th className="p-2 font-medium">Regla</th>
                                <th className="p-2 font-medium">Estado</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {contractualEvals.filter(e => e.supplier_offer_id === offer.id).map((c, idx) => (
                                <tr key={idx}>
                                  <td className="p-2">{c.label || c.key}</td>
                                  <td className="p-2 font-medium">{c.required_value}</td>
                                  <td className="p-2">{c.offered_value || '-'}</td>
                                  <td className="p-2 text-xs text-gray-500">{c.resolution_rule}</td>
                                  <td className="p-2">{getStatusBadge(c.status)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          </div>
        </>
      )}
    </div>
  );
};
