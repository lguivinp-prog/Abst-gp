import React, { useState, useEffect, useMemo } from 'react';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { casesService } from '../../../api/cases.service';
import { evaluationService } from '../../../api/v6/evaluation.service';
import { Trophy, AlertTriangle, CheckCircle2, Info, Star } from 'lucide-react';
import './CaseEvaluations.css';

interface CaseSelectionProps {
  caseId: string;
}

export const CaseSelection: React.FC<CaseSelectionProps> = ({ caseId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<any | null>(null);
  const [offers, setOffers] = useState<any[]>([]);
  const [vfmRanking, setVfmRanking] = useState<any[]>([]);
  const [selectedOfferId, setSelectedOfferId] = useState<number | null>(null);
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadData();
  }, [caseId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [selRes, offRes, vfmRes] = await Promise.all([
        casesService.getSelection(caseId).catch(() => null),
        casesService.getOffers(caseId).catch(() => []),
        evaluationService.getVFMRanking(caseId).catch(() => [])
      ]);
      setSelection(selRes);
      setOffers(Array.isArray(offRes) ? offRes : []);
      setVfmRanking(Array.isArray(vfmRes) ? vfmRes : []);
    } catch (err: any) {
      setError(err.message || 'Error al cargar datos de selección');
    } finally {
      setLoading(false);
    }
  };

  // Identificar la mejor recomendación determinista (Elegible #1 en VfM)
  const topRecommendation = useMemo(() => {
    const eligible = (vfmRanking || []).filter((r: any) => r.is_eligible);
    return eligible.length > 0 ? eligible[0] : null;
  }, [vfmRanking]);

  const recommendedOffer = useMemo(() => {
    if (!topRecommendation) return null;
    return offers.find((o) => o.id === topRecommendation.supplier_offer_id);
  }, [topRecommendation, offers]);

  const handlePropose = async (offerId: number) => {
    const isDivergent = topRecommendation && offerId !== topRecommendation.supplier_offer_id;
    const isNoRec = !topRecommendation;

    // Validación en Frontend de Justificación Expresa (Requisito 4 y 5 de Etapa 3)
    if ((isDivergent || isNoRec) && !justification.trim()) {
      setError('Debe fundamentar expresamente el motivo de la propuesta seleccionada.');
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await casesService.proposeSelection(caseId, {
        supplier_offer_id: offerId,
        justification_comment: justification.trim() || undefined
      });
      await loadData();
      setJustification('');
      setSelectedOfferId(null);
    } catch (err: any) {
      setError(err.message || 'Error al registrar la propuesta de selección');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="case-evaluations-loading">
        <div className="spinner"></div>
        <p>Cargando opciones de selección y recomendaciones...</p>
      </div>
    );
  }

  return (
    <div className="v6-evaluations-container">
      <div className="v6-evaluations-header">
        <div>
          <h2 className="v6-evaluations-title">Propuesta de Selección Fundamentada</h2>
          <p className="v6-evaluations-subtitle">
            Selección técnica y económica sustentada para revisión y aprobación interna del expediente.
          </p>
        </div>
      </div>

      {error && (
        <div className="case-evaluations-error mb-4 flex items-center gap-2">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* ESTADO ACTUAL: PROPUESTA EN REVISIÓN */}
      {selection && (
        <div className="mb-6 p-4 border rounded-lg bg-blue-50 border-blue-200">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-bold flex items-center gap-2 text-blue-900 text-base">
              <Trophy size={18} className="text-blue-700" />
              Propuesta de Selección Registrada
            </h3>
            <Badge variant={selection.status === 'APPROVED' ? 'success' : 'primary'}>
              {selection.status === 'UNDER_REVIEW' ? 'En Revisión por Supervisión' : selection.status}
            </Badge>
          </div>
          <div className="text-sm text-blue-950 space-y-1">
            <p><strong>Oferta Propuesta:</strong> #{selection.supplier_offer_id}</p>
            <p><strong>Justificación Registrada:</strong> {selection.justification_comment || 'Ninguna (coincidente con recomendación determinista)'}</p>
            <p className="text-xs text-blue-800 pt-1 border-t border-blue-200">
              Esta propuesta se encuentra a la espera de aprobación interna en el módulo de Resultados.
            </p>
          </div>
        </div>
      )}

      {/* BANNER DE RECOMENDACIÓN DETERMINISTA DEL SISTEMA (Requisito 2 y 3) */}
      {!selection && (
        <>
          {topRecommendation ? (
            <div className="mb-6 p-4 border border-emerald-200 rounded-lg bg-emerald-50 text-emerald-950 flex items-start gap-3">
              <Star size={20} className="text-emerald-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm space-y-0.5">
                <p className="font-bold text-emerald-900 flex items-center gap-2">
                  Indicador Referencial de Valor por Dinero (VfM)
                </p>
                <p className="text-xs text-emerald-800">
                  Proveedor referencial: <strong>{recommendedOffer?.supplier?.business_name || `Proveedor #${topRecommendation.supplier_id}`}</strong> (RUC: {recommendedOffer?.supplier?.ruc || 'N/A'})
                </p>
                <p className="text-xs text-emerald-800">
                  Puntaje Técnico: {topRecommendation.total_score} pts | Ratio VfM: {topRecommendation.vfm_ratio?.toFixed(2)} | Precio: {recommendedOffer?.currency || 'PEN'} {recommendedOffer?.total_amount != null ? Number(recommendedOffer.total_amount).toLocaleString('es-PE', { minimumFractionDigits: 2 }) : '-'}
                </p>
                <p className="text-[11px] text-emerald-700 pt-1 italic">
                  Este indicador es referencial y de apoyo a la decisión administrativa; no sustituye la evaluación técnica ni vincula normativamente la adjudicación. Proponer una opción diferente requerirá justificación motivada.
                </p>
              </div>
            </div>
          ) : (
            <div className="mb-6 p-4 border border-amber-200 rounded-lg bg-amber-50 text-amber-950 flex items-start gap-3">
              <Info size={20} className="text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm space-y-0.5">
                <p className="font-bold text-amber-900">
                  Sin Recomendación Determinista Confiable
                </p>
                <p className="text-xs text-amber-800">
                  El sistema no cuenta con suficientes ofertas evaluadas elegibles para emitir una recomendación objetiva automática.
                  Cualquier propuesta que formule el operador exigirá motivación y justificación humana obligatoria.
                </p>
              </div>
            </div>
          )}
        </>
      )}

      {/* LISTADO DE OFERTAS CANDIDATAS */}
      <div className="v6-eval-list space-y-4">
        {offers.length === 0 ? (
          <div className="p-6 bg-gray-50 border rounded text-center text-gray-500">
            No hay ofertas registradas en este expediente.
          </div>
        ) : (
          offers.map((offer) => {
            const hasPrice =
              (offer.total_amount !== null && offer.total_amount !== undefined) ||
              (offer.price !== null && offer.price !== undefined);
            const isOfferComplete = offer.status !== 'PENDING' && hasPrice;
            const displayPrice = offer.total_amount ?? offer.price;
            const vfm = vfmRanking.find((r) => r.supplier_offer_id === offer.id);

            const isTopRec = topRecommendation && offer.id === topRecommendation.supplier_offer_id;
            const isDivergent = topRecommendation && offer.id !== topRecommendation.supplier_offer_id;
            const isSelected = selectedOfferId === offer.id;

            return (
              <div
                key={offer.id}
                className={`p-5 border rounded-lg transition-all ${
                  isTopRec
                    ? 'border-emerald-300 bg-emerald-50/30'
                    : 'border-gray-200 bg-white'
                }`}
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <h3 className="font-bold text-base text-gray-900">
                        {offer.supplier?.business_name || `Proveedor #${offer.supplier_id}`}
                      </h3>
                      {isTopRec && (
                        <Badge variant="success" className="text-xs flex items-center gap-1">
                          <CheckCircle2 size={12} />
                          Recomendación Principal
                        </Badge>
                      )}
                      {isDivergent && (
                        <Badge variant="warning" className="text-xs flex items-center gap-1">
                          <AlertTriangle size={12} />
                          Propuesta Divergente
                        </Badge>
                      )}
                      {!isOfferComplete && (
                        <Badge variant="danger" className="text-xs">
                          Incompleta / Pendiente
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-gray-500">
                      RUC: {offer.supplier?.ruc || 'No registrado'} | Estado Oferta: {offer.status}
                    </p>
                  </div>

                  <div className="text-right">
                    <span className="text-xs text-gray-500 block">Importe Económico Ofertado</span>
                    <span className="text-base font-bold text-gray-900">
                      {displayPrice != null
                        ? `${offer.currency || 'PEN'} ${Number(displayPrice).toLocaleString('es-PE', { minimumFractionDigits: 2 })}`
                        : 'No definido'}
                    </span>
                    {vfm && vfm.is_eligible && (
                      <span className="text-xs text-blue-700 block mt-0.5">
                        Puntaje: {vfm.total_score} | Ratio: {vfm.vfm_ratio?.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>

                {!selection && isOfferComplete && (
                  <div className="mt-4 pt-4 border-t border-gray-100">
                    {/* Alerta de Divergencia si se propone una oferta distinta */}
                    {isDivergent && (
                      <div className="mb-3 p-2.5 rounded bg-amber-50 border border-amber-200 text-xs text-amber-900 flex items-start gap-2">
                        <AlertTriangle size={15} className="text-amber-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <strong>Atención: Selección divergente de la recomendación objetiva.</strong>
                          <p>
                            Esta opción difiere de la oferta con mejor ratio determinista ({recommendedOffer?.supplier?.business_name || 'Proveedor #1'}).
                            Es <strong>obligatorio fundamentar expresamente</strong> los motivos técnicos o de mercado.
                          </p>
                        </div>
                      </div>
                    )}

                    {!topRecommendation && (
                      <div className="mb-3 p-2.5 rounded bg-blue-50 border border-blue-200 text-xs text-blue-900 flex items-start gap-2">
                        <Info size={15} className="text-blue-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <strong>Sin recomendación previa del sistema.</strong>
                          <p>Es obligatorio ingresar la fundamentación que sustenta la elección de este proveedor.</p>
                        </div>
                      </div>
                    )}

                    <div className="space-y-2">
                      <label className="block text-xs font-semibold text-gray-700">
                        {isDivergent
                          ? 'Justificación expresa de la selección divergente *'
                          : !topRecommendation
                          ? 'Fundamentación obligatoria de la propuesta *'
                          : 'Justificación técnica (opcional)'}
                      </label>
                      <textarea
                        rows={2}
                        placeholder={
                          isDivergent || !topRecommendation
                            ? 'Indique detalladamente el motivo técnico, operativo o de conveniencia institucional...'
                            : 'Comentarios adicionales sobre la propuesta recomendada (opcional)...'
                        }
                        value={isSelected ? justification : ''}
                        onFocus={() => setSelectedOfferId(offer.id)}
                        onChange={(e) => {
                          setSelectedOfferId(offer.id);
                          setJustification(e.target.value);
                        }}
                        className="border border-gray-300 p-2 text-xs w-full rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                        disabled={submitting}
                      />

                      <div className="flex justify-end pt-1">
                        <Button
                          onClick={() => handlePropose(offer.id)}
                          disabled={
                            submitting ||
                            !isOfferComplete ||
                            ((isDivergent || !topRecommendation) && (!isSelected || !justification.trim()))
                          }
                          variant={isTopRec ? 'primary' : 'outline'}
                          title={
                            (isDivergent || !topRecommendation) && (!isSelected || !justification.trim())
                              ? 'Debe ingresar una justificación para continuar con esta propuesta.'
                              : ''
                          }
                        >
                          {submitting && isSelected ? 'Registrando...' : 'Proponer Selección'}
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                {!isOfferComplete && !selection && (
                  <p className="text-xs text-gray-400 italic mt-2">
                    Esta oferta no cuenta con precios completos o se encuentra en estado pendiente. No es elegible para propuesta.
                  </p>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
