import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  RefreshCw,
  BarChart2,
  Table as TableIcon,
  List as ListIcon,
  Info,
  ShieldAlert,
  FileText
} from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { evaluationService } from '../../../api/v6/evaluation.service';
import type { EvaluationResponse } from '../../../api/v6/evaluation.types';
import { offerService } from '../../../api/v6/offer.service';
import type { SupplierOfferResponse } from '../../../api/v6/offer.types';
import { requirementsService } from '../../../api/v6/requirements.service';
import type { RequirementResponse } from '../../../api/v6/requirements.types';
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
  const [requirements, setRequirements] = useState<RequirementResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<number | null>(null);
  const [activeView, setActiveView] = useState<'matrix' | 'cards'>('cards');
  const userManuallyToggledViewRef = useRef<boolean>(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [evalsRes, offersRes, contractualRes, vfmRes, reqsRes] = await Promise.allSettled([
        evaluationService.getCaseEvaluations(caseId),
        offerService.getOffers(caseId),
        evaluationService.getContractualEvaluations(caseId),
        evaluationService.getVFMRanking(caseId),
        requirementsService.getRequirements(caseId)
      ]);

      const failedServices: string[] = [];
      if (evalsRes.status === 'rejected') failedServices.push('Evaluaciones');
      if (offersRes.status === 'rejected') failedServices.push('Ofertas');
      if (contractualRes.status === 'rejected') failedServices.push('Condiciones Contractuales');
      if (vfmRes.status === 'rejected') failedServices.push('Ranking VfM');
      if (reqsRes.status === 'rejected') failedServices.push('Requisitos');

      if (failedServices.length > 0) {
        setError(`Error al consultar servicios de datos: ${failedServices.join(', ')}. La información mostrada puede estar incompleta.`);
      }

      setEvaluations(evalsRes.status === 'fulfilled' ? evalsRes.value : []);
      const loadedOffers = offersRes.status === 'fulfilled' ? offersRes.value : [];
      setOffers(loadedOffers);
      if (!userManuallyToggledViewRef.current) {
        if (loadedOffers.length >= 2) {
          setActiveView('matrix');
        } else {
          setActiveView('cards');
        }
      }
      setContractualEvals(contractualRes.status === 'fulfilled' ? contractualRes.value : []);
      setVfmRanking(vfmRes.status === 'fulfilled' ? vfmRes.value : []);
      setRequirements(reqsRes.status === 'fulfilled' ? reqsRes.value : []);
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
    userManuallyToggledViewRef.current = false;
    loadData();
  }, [caseId]);

  const handleSelectView = (view: 'matrix' | 'cards') => {
    userManuallyToggledViewRef.current = true;
    setActiveView(view);
  };

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

  // Up to 10 suppliers for multi-supplier comparative matrix
  const comparedOffers = useMemo(() => {
    return offers.slice(0, 10);
  }, [offers]);

  // Requisitos validados legítimos desde la API de requerimientos (sin crear requisitos ficticios)
  const allRequirements = useMemo(() => {
    return requirements;
  }, [requirements]);

  // Distinct contractual condition keys across all offers
  const distinctContractualKeys = useMemo(() => {
    const map = new Map<string, { key: string; label: string; required_value: string }>();
    contractualEvals.forEach(c => {
      const k = c.key || c.label;
      if (!map.has(k)) {
        map.set(k, {
          key: c.key,
          label: c.label || c.key,
          required_value: c.required_value || '-'
        });
      }
    });
    return Array.from(map.values());
  }, [contractualEvals]);

  // Check if comparison is complete or in-progress (Requisito 10)
  const isComparisonIncomplete = useMemo(() => {
    if (comparedOffers.length === 0) return true;
    return comparedOffers.some(o => {
      const offerEvals = evaluations.filter(e => e.supplier_offer_id === o.id);
      const isIncompleteOffer = o.status === 'PENDING' && !o.price && !o.total_amount;
      return isIncompleteOffer || offerEvals.length === 0;
    });
  }, [comparedOffers, evaluations]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PASSED':
      case 'CUMPLE':
        return <Badge variant="success"><CheckCircle2 size={13} className="mr-1" /> Cumple</Badge>;
      case 'IMPROVEMENT':
      case 'CUMPLE_Y_MEJORA':
        return <Badge variant="success"><CheckCircle2 size={13} className="mr-1" /> Cumple y Mejora</Badge>;
      case 'CONFLICT':
      case 'NO_CUMPLE':
        return <Badge variant="danger"><XCircle size={13} className="mr-1" /> No Cumple</Badge>;
      case 'MISSING_DATA':
      case 'NO_OFERTADO':
        return <Badge variant="warning"><AlertTriangle size={13} className="mr-1" /> Inf. Faltante</Badge>;
      case 'REQUIERE_REVISION':
        return <Badge variant="warning"><AlertTriangle size={13} className="mr-1" /> Revisión Necesaria</Badge>;
      default:
        return <Badge variant="secondary"><Clock size={13} className="mr-1" /> {status || 'Pendiente'}</Badge>;
    }
  };

  if (loading && offers.length === 0) {
    return (
      <div className="case-evaluations-loading">
        <div className="spinner"></div>
        <p>Cargando matriz comparativa y evaluaciones...</p>
      </div>
    );
  }

  return (
    <div className="case-evaluations-container">
      <div className="case-evaluations-header">
        <div>
          <h2>Matriz Comparativa y Evaluación Técnica</h2>
          <p>Comparación multiproveedor (2 a 10 proveedores) contrastada objetivamente con los requisitos validados.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="view-toggle flex rounded border border-gray-200 overflow-hidden bg-gray-50">
            <button
              onClick={() => handleSelectView('matrix')}
              className={`px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 transition-colors ${
                activeView === 'matrix' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              <TableIcon size={14} />
              Matriz Multiproveedor
            </button>
            <button
              onClick={() => handleSelectView('cards')}
              className={`px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 transition-colors ${
                activeView === 'cards' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              <ListIcon size={14} />
              Detalle por Oferta
            </button>
          </div>
          <Button variant="outline" onClick={loadData}>
            <RefreshCw size={15} className="mr-1.5" />
            Actualizar
          </Button>
        </div>
      </div>

      {error && (
        <div className="case-evaluations-error">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {/* Alerta de Integridad (Requisito 10): No permitir que una comparación incompleta aparezca como concluida */}
      {isComparisonIncomplete && offers.length > 0 && (
        <div className="p-4 mb-6 rounded-md bg-amber-50 border border-amber-200 text-amber-900 text-sm flex items-start gap-3">
          <ShieldAlert size={20} className="text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold mb-0.5">Comparación Técnica en Curso / Información Incompleta</p>
            <p className="text-xs text-amber-800">
              Uno o más proveedores tienen ofertas sin evaluar o con datos pendientes. Esta matriz no debe considerarse como evaluación técnica concluida ni decisión final hasta completar la evaluación de todas las ofertas.
            </p>
          </div>
        </div>
      )}

      {offers.length === 0 ? (
        <div className="case-evaluations-empty">
          <BarChart2 size={48} className="empty-icon" />
          <h3>No hay ofertas para evaluar</h3>
          <p>Aún no se han recibido ofertas o vinculado proveedores a este expediente.</p>
        </div>
      ) : activeView === 'matrix' ? (
        <div className="space-y-8">
          {/* VISTA 1: MATRIZ COMPARATIVA MULTIPROVEEDOR (ETAPA 2) */}
          <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
            <div className="p-4 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
              <div>
                <h3 className="text-base font-semibold text-gray-900">
                  Matriz Comparativa Multiproveedor ({comparedOffers.length} {comparedOffers.length === 1 ? 'proveedor' : 'proveedores'})
                </h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Requisitos técnicos validados como referencia común en filas vs. ofertas recibidas en columnas.
                </p>
              </div>
              <div className="text-xs text-gray-500">
                Límite normativo PRD: hasta 10 proveedores simultáneos
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left border-collapse">
                <thead>
                  <tr className="bg-gray-100 border-b border-gray-200 text-gray-700">
                    <th className="p-3 w-80 min-w-[280px] font-semibold border-r border-gray-200 bg-gray-100 sticky left-0 z-10">
                      Requisitos Validados del Expediente
                    </th>
                    {comparedOffers.map((offer, idx) => {
                      const displayPrice = offer.total_amount != null ? offer.total_amount : offer.price;
                      const currencyStr = offer.currency || 'PEN';
                      const offerEvals = evaluations.filter((e) => e.supplier_offer_id === offer.id);
                      const isEvaluated = offerEvals.length > 0;
                      const isIncomplete = offer.status === 'PENDING' && !offer.price && !offer.total_amount && !offer.source_document;
                      return (
                        <th key={offer.id} className="p-3 min-w-[220px] max-w-[260px] font-semibold border-r border-gray-200 align-top">
                          <div className="flex flex-col gap-1">
                            <span className="text-xs font-bold text-blue-700 uppercase">Proveedor #{idx + 1}</span>
                            <span className="text-sm font-semibold text-gray-900 truncate" title={offer.supplier?.business_name}>
                              {offer.supplier?.business_name || `Proveedor #${offer.supplier_id}`}
                            </span>
                            <span className="text-xs text-gray-500 font-normal">
                              RUC: {offer.supplier?.ruc || 'No registrado'}
                            </span>
                            <div className="mt-1 pt-1 border-t border-gray-200 flex justify-between items-center text-xs">
                              <span className="text-gray-500 font-normal">Económica:</span>
                              <span className="font-semibold text-gray-800">
                                {displayPrice != null ? `${currencyStr} ${Number(displayPrice).toLocaleString('es-PE', { minimumFractionDigits: 2 })}` : 'Sin precio'}
                              </span>
                            </div>
                            <div className="mt-2">
                              {isIncomplete ? (
                                <span className="text-xs text-gray-400 italic">Oferta incompleta</span>
                              ) : (
                                <Button
                                  onClick={() => handleEvaluateOffer(offer.id)}
                                  disabled={isEvaluating === offer.id}
                                  variant={isEvaluated ? 'outline' : 'primary'}
                                  className="w-full text-xs py-1"
                                >
                                  {isEvaluating === offer.id ? 'Evaluando...' : isEvaluated ? 'Re-evaluar Oferta' : 'Evaluar Oferta'}
                                </Button>
                              )}
                            </div>
                          </div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {/* SECCIÓN 1: REQUISITOS TÉCNICOS */}
                  <tr className="bg-blue-50 font-semibold text-blue-950 text-xs uppercase tracking-wide">
                    <td colSpan={comparedOffers.length + 1} className="p-2.5 pl-3">
                      1. Requisitos Técnicos y Documentales (Resultados de Requisitos)
                    </td>
                  </tr>

                  {allRequirements.length === 0 ? (
                    <tr>
                      <td colSpan={comparedOffers.length + 1} className="p-4 text-center text-gray-500 italic">
                        No hay requisitos registrados para este expediente.
                      </td>
                    </tr>
                  ) : (
                    allRequirements.map((req) => (
                      <tr key={req.id} className="hover:bg-gray-50">
                        <td className="p-3 border-r border-gray-200 bg-white sticky left-0 z-10 align-top">
                          <div className="flex flex-col gap-1">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <Badge variant="secondary" className="text-[10px]">
                                {req.requirement_type || 'TÉCNICO'} #{req.id}
                              </Badge>
                              {req.mandatory && (
                                <Badge variant="warning" className="text-[10px]">Obligatorio</Badge>
                              )}
                              {req.evidences && req.evidences.length > 0 && req.evidences[0].source_page != null && (
                                <span className="text-[10px] text-gray-500 font-medium bg-gray-100 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                                  <FileText size={10} />
                                  Pág. {req.evidences[0].source_page}
                                </span>
                              )}
                            </div>
                            <span className="text-xs font-medium text-gray-900 leading-tight">
                              {req.description}
                            </span>
                          </div>
                        </td>

                        {comparedOffers.map((offer) => {
                          const ev = evaluations.find(
                            (e) => e.supplier_offer_id === offer.id && e.requirement_id === req.id
                          );
                          const isUnevaluated = !ev;
                          const isIncomplete = offer.status === 'PENDING' && !offer.price && !offer.total_amount;

                          return (
                            <td key={offer.id} className="p-3 border-r border-gray-200 align-top text-xs">
                              {isIncomplete ? (
                                <span className="text-gray-400 italic">Oferta incompleta</span>
                              ) : isUnevaluated ? (
                                <span className="text-gray-400 italic">No evaluado</span>
                              ) : (
                                <div className="space-y-1.5">
                                  <div>{getStatusBadge(ev.status)}</div>
                                  {ev.explanation && (
                                    <p className="text-xs text-gray-600 line-clamp-3 leading-snug" title={ev.explanation}>
                                      {ev.explanation}
                                    </p>
                                  )}
                                  <div className="flex items-center gap-2 pt-1 border-t border-gray-100 text-[10px] text-gray-500">
                                    {ev.evaluation_confidence != null && (
                                      <span>Confianza: {(ev.evaluation_confidence * 100).toFixed(0)}%</span>
                                    )}
                                    {ev.status === 'REQUIERE_REVISION' && (
                                      <span className="text-amber-700 font-semibold">⚠️ Revisión humana</span>
                                    )}
                                  </div>
                                </div>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))
                  )}

                  {/* SECCIÓN 2: CONDICIONES CONTRACTUALES Y MEJORAS */}
                  {distinctContractualKeys.length > 0 && (
                    <>
                      <tr className="bg-purple-50 font-semibold text-purple-950 text-xs uppercase tracking-wide">
                        <td colSpan={comparedOffers.length + 1} className="p-2.5 pl-3">
                          2. Condiciones Contractuales y Mejoras
                        </td>
                      </tr>

                      {distinctContractualKeys.map((condKey) => (
                        <tr key={condKey.key} className="hover:bg-gray-50">
                          <td className="p-3 border-r border-gray-200 bg-white sticky left-0 z-10 align-top">
                            <span className="text-xs font-semibold text-gray-900 block">{condKey.label}</span>
                            <span className="text-[11px] text-gray-500">Requerido: {condKey.required_value}</span>
                          </td>

                          {comparedOffers.map((offer) => {
                            const c = contractualEvals.find(
                              (item) => item.supplier_offer_id === offer.id && (item.key === condKey.key || item.label === condKey.label)
                            );

                            return (
                              <td key={offer.id} className="p-3 border-r border-gray-200 align-top text-xs">
                                {!c ? (
                                  <span className="text-gray-400 italic">-</span>
                                ) : (
                                  <div className="space-y-1">
                                    <div>{getStatusBadge(c.status)}</div>
                                    <div className="text-xs">
                                      <span className="text-gray-500">Ofertado: </span>
                                      <span className="font-medium text-gray-800">{c.offered_value || '-'}</span>
                                    </div>
                                    {c.status === 'CUMPLE_Y_MEJORA' && (
                                      <span className="inline-block text-[10px] text-purple-700 font-semibold bg-purple-50 px-1.5 py-0.5 rounded">
                                        + Mejora técnica
                                      </span>
                                    )}
                                  </div>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </>
                  )}

                  {/* SECCIÓN 3: INFORMACIÓN ECONÓMICA SEPARADA */}
                  <tr className="bg-emerald-50 font-semibold text-emerald-950 text-xs uppercase tracking-wide">
                    <td colSpan={comparedOffers.length + 1} className="p-2.5 pl-3">
                      3. Oferta Económica (Términos Comerciales Visibles)
                    </td>
                  </tr>
                  <tr>
                    <td className="p-3 border-r border-gray-200 bg-white sticky left-0 z-10 align-top">
                      <span className="text-xs font-semibold text-gray-900 block">Precio Total de la Oferta</span>
                      <span className="text-[10px] text-gray-500">
                        La información económica no constituye por sí sola mérito técnico.
                      </span>
                    </td>
                    {comparedOffers.map((offer) => {
                      const displayPrice = offer.total_amount != null ? offer.total_amount : offer.price;
                      const currencyStr = offer.currency || 'PEN';
                      const vfmItem = vfmRanking.find((r) => r.supplier_offer_id === offer.id);

                      return (
                        <td key={offer.id} className="p-3 border-r border-gray-200 align-top text-xs">
                          <div className="space-y-1">
                            <span className="text-sm font-bold text-emerald-800 block">
                              {displayPrice != null
                                ? `${currencyStr} ${Number(displayPrice).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`
                                : 'No especificado'}
                            </span>
                            {vfmItem && (
                              <div className="pt-1 text-[11px] text-gray-600 space-y-0.5">
                                <div>
                                  Elegibilidad: {vfmItem.is_eligible ? (
                                    <span className="text-emerald-700 font-medium">Elegible</span>
                                  ) : (
                                    <span className="text-red-700 font-medium">Descalificado</span>
                                  )}
                                </div>
                                {vfmItem.is_eligible && (
                                  <div>
                                    Ratio VfM: <span className="font-semibold text-blue-700">{vfmItem.vfm_ratio?.toFixed(2)}</span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="p-3 bg-gray-50 border-t border-gray-200 text-xs text-gray-500 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Info size={14} className="text-blue-600" />
                <span>Precios y condiciones visibles sin reemplazo de la decisión técnica colegiada ni asignación automática de derechos.</span>
              </div>
            </div>
          </div>

          {/* RANKING DETERMINISTA VFM */}
          {vfmRanking && vfmRanking.length > 0 && (
            <div className="border border-blue-200 rounded-lg overflow-hidden bg-white shadow-sm">
              <div className="p-4 bg-blue-50 border-b border-blue-100 flex justify-between items-center">
                <div>
                  <h3 className="text-sm font-semibold text-blue-900">
                    Ranking Determinista de Valor por Dinero (VFM)
                  </h3>
                  <p className="text-xs text-blue-700 mt-0.5">
                    Clasificación objetiva calculada mediante ratio precio/puntos técnicos de ofertas elegibles.
                  </p>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-blue-100 text-blue-900 border-b border-blue-200">
                    <tr>
                      <th className="p-3 font-semibold text-center w-16">Orden</th>
                      <th className="p-3 font-semibold">Proveedor</th>
                      <th className="p-3 font-semibold">Estado Técnico</th>
                      <th className="p-3 font-semibold text-right">Puntaje Técnico</th>
                      <th className="p-3 font-semibold text-right">Precio Ofertado</th>
                      <th className="p-3 font-semibold text-right">Ratio (Precio/Pto)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-blue-100 bg-white">
                    {vfmRanking.map((vfm, idx) => {
                      const off = offers.find((o) => o.id === vfm.supplier_offer_id);
                      const provName = off?.supplier?.business_name || `Proveedor #${vfm.supplier_id}`;
                      const currencyStr = off?.currency === 'USD' ? 'US$' : 'S/';

                      return (
                        <tr key={vfm.supplier_offer_id} className={!vfm.is_eligible ? 'opacity-60 bg-gray-50' : ''}>
                          <td className="p-3 text-center font-bold text-gray-600">
                            {vfm.is_eligible ? `#${idx + 1}` : '-'}
                          </td>
                          <td className="p-3 font-medium text-gray-900">
                            {provName}
                            {vfm.is_eligible && idx === 0 && (
                              <Badge variant="success" className="ml-2 text-[10px]">Mejor Recomendación</Badge>
                            )}
                          </td>
                          <td className="p-3">
                            {vfm.is_eligible ? (
                              <Badge variant="success">Elegible</Badge>
                            ) : (
                              <Badge variant="danger">Descalificado: {vfm.reason || 'Condiciones no cumplidas'}</Badge>
                            )}
                          </td>
                          <td className="p-3 text-right">{vfm.is_eligible ? vfm.total_score : '-'}</td>
                          <td className="p-3 text-right">
                            {vfm.is_eligible && vfm.price != null
                              ? `${currencyStr} ${Number(vfm.price).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`
                              : '-'}
                          </td>
                          <td className="p-3 text-right font-semibold text-blue-700">
                            {vfm.is_eligible && vfm.vfm_ratio != null ? vfm.vfm_ratio.toFixed(2) : '-'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* VISTA 2: DETALLE POR OFERTA (EVALUACIÓN Y RE-EVALUACIÓN INDIVIDUAL) */
        <div className="case-evaluations-list">
          {offers.map((offer) => {
            const offerEvals = evaluations.filter((e) => e.supplier_offer_id === offer.id);
            const isEvaluated = offerEvals.length > 0;
            const isIncomplete = offer.status === 'PENDING' && !offer.price && !offer.total_amount && !offer.source_document;
            const displayPrice = offer.total_amount != null ? offer.total_amount : offer.price;

            return (
              <div key={offer.id} className="evaluation-card">
                <div className="evaluation-header">
                  <div className="offer-info">
                    <h4>{offer.supplier?.business_name || `Proveedor #${offer.supplier_id}`}</h4>
                    <span className="offer-price">
                      {displayPrice !== undefined && displayPrice !== null
                        ? `Precio: ${offer.currency || 'PEN'} ${Number(displayPrice).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`
                        : 'Sin oferta económica definida'}
                    </span>
                  </div>
                  <div className="evaluation-actions">
                    {isIncomplete ? (
                      <span className="incomplete-text">Oferta incompleta</span>
                    ) : (
                      <Button
                        onClick={() => handleEvaluateOffer(offer.id)}
                        disabled={isEvaluating === offer.id}
                        variant={isEvaluated ? 'outline' : 'primary'}
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
                      {offerEvals.map((evalItem) => (
                        <div key={evalItem.id} className="result-item">
                          <div className="result-status">{getStatusBadge(evalItem.status)}</div>
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
                                Confianza determinista: {(evalItem.evaluation_confidence * 100).toFixed(1)}%
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div className="mt-6 border-t pt-4">
                      <h5 className="mb-4">Matriz de Cumplimiento Contractual</h5>
                      {contractualEvals.filter((e) => e.supplier_offer_id === offer.id).length === 0 ? (
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
                              {contractualEvals
                                .filter((e) => e.supplier_offer_id === offer.id)
                                .map((c, idx) => (
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
      )}
    </div>
  );
};
