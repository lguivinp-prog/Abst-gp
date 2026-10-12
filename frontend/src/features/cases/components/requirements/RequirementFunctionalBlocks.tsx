import React from 'react';
import type { RequirementResponse, ProcurementItemResponse } from '../../../../api/v6/requirements.types';
import { Badge } from '../../../../components/ui/Badge';
import { Button } from '../../../../components/ui/Button';
import { Edit2 } from 'lucide-react';

interface Props {
  requirements: RequirementResponse[];
  procurementItems: ProcurementItemResponse[];
  onEditRequirement: (req: RequirementResponse) => void;
  isTerminal?: boolean;
}

export const RequirementFunctionalBlocks: React.FC<Props> = ({
  requirements,
  procurementItems,
  onEditRequirement,
  isTerminal = false,
}) => {
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PENDING_REVIEW': return <Badge variant="warning">Pendiente</Badge>;
      case 'REVIEW_REQUIRED': return <Badge variant="danger">Revisar Extracción</Badge>;
      case 'VALIDATED': return <Badge variant="success">Validado</Badge>;
      case 'OBSERVED': return <Badge variant="danger">Observado</Badge>;
      case 'REJECTED': return <Badge variant="danger">Rechazado</Badge>;
      case 'MODIFIED_BY_USER': return <Badge variant="primary">Modificado</Badge>;
      default: return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const normalizeString = (str: string) => {
    if (!str) return '';
    return str
      .toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[.,:;()\-]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  };

  const getUnrepresentedSpecs = (item: ProcurementItemResponse) => {
    const itemMatrices = itemSpecReqs.filter(r => r.procurement_item_id === item.id);
    if (itemMatrices.length === 0) return [];
    
    return itemMatrices.filter(matrix => {
      const matrixName = normalizeString(matrix.description);
      const matrixVal = normalizeString(matrix.value || '');
      const matrixCombined = `${matrixName} ${matrixVal}`.trim();
      
      const isRepresented = item.specifications.some(spec => {
        const specName = normalizeString(spec.name);
        const specVal = normalizeString(spec.value);
        const specCombined = `${specName} ${specVal}`.trim();
        return specCombined.includes(matrixCombined);
      });
      return !isRepresented;
    });
  };

  const cleanDescription = (desc: string) => {
    if (!desc) return desc;
    return desc.replace(/^[\uf0b7\u2022\-\s]+/, '');
  };

  const contextReqs = requirements.filter(r => r.category === 'CONTEXT');
  const obligationReqs = requirements.filter(r => r.category === 'GENERAL_OBLIGATION');
  const itemSpecReqs = requirements.filter(r => r.category === 'ITEM_SPECIFICATION');
  const contractualReqs = requirements.filter(r => r.category === 'CONTRACTUAL_TERM' || r.requirement_type === 'CONTRACTUAL');
  const selectionReqs = requirements.filter(r => r.category === 'SELECTION_REQUIREMENT');

  const renderRequirementTable = (reqs: RequirementResponse[], title: string, subtitle: string, columns: {label: string, render: (req: RequirementResponse) => React.ReactNode}[]) => (
    <>
      <div className="case-requirements__header-wrapper mt-8">
        <div className="case-requirements__header">
          <h2 className="case-requirements__title">{title}</h2>
          <p className="case-requirements__subtitle">{subtitle}</p>
        </div>
      </div>
      <div className="case-requirements__list mb-6">
        {reqs.length === 0 ? (
          <div className="case-requirements__card case-requirements__empty">
            <p>No se han identificado registros para esta sección.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left border-collapse" style={{ minWidth: '800px' }}>
              <thead className="bg-gray-50 border-b">
                <tr>
                  {columns.map((col, idx) => <th key={idx} className="p-3 font-semibold whitespace-nowrap">{col.label}</th>)}
                  <th className="p-3 font-semibold w-24 text-right">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {reqs.map(req => (
                  <tr key={req.id}>
                    {columns.map((col, idx) => <td key={idx} className="p-3 align-top">{col.render(req)}</td>)}
                    <td className="p-3 text-right align-top">
                      <Button variant="ghost" size="sm" onClick={() => onEditRequirement(req)} disabled={isTerminal}>
                        <Edit2 size={16} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );

  return (
    <div className="requirements-functional-blocks">
      {/* A. Especificaciones por Ítem */}
      {procurementItems.length > 0 && (
        <div className="mt-4">
          <h4 className="text-sm font-semibold text-blue-800 mb-2">Especificaciones Estructuradas por Ítem</h4>
          <div className="grid gap-4">
            {procurementItems.map(item => {
              const unrepresentedSpecs = getUnrepresentedSpecs(item);
              return (
                <div key={item.id} className="case-requirements__card bg-white border border-gray-200">
                  <div className="font-semibold text-gray-800 mb-2">
                    Ítem {item.item_number || item.id}: {item.description}
                  </div>
                  {item.specifications && item.specifications.length > 0 ? (
                    <ul className="list-disc pl-5 text-sm text-gray-700">
                      {item.specifications.map(spec => (
                        <li key={spec.id}>
                          <span className="font-medium">{spec.name}:</span> {spec.value}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-gray-500 italic">Sin especificaciones estructuradas</p>
                  )}
                  
                  {unrepresentedSpecs.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-gray-100">
                      <h5 className="text-xs font-semibold text-orange-600 mb-2">Información extraída pendiente de conciliación</h5>
                      <div className="grid gap-2">
                        {unrepresentedSpecs.map(req => (
                          <div key={req.id} className="flex items-center justify-between py-1 text-xs bg-orange-50 px-2 rounded">
                            <div>
                              <span className="font-medium">{req.description}</span>
                              {req.value && <span className="ml-1 text-gray-600">: {req.value}</span>}
                              {req.numeric_value !== null && <span className="ml-1 text-gray-600">: {req.numeric_value} {req.unit}</span>}
                              {req.evidences?.[0]?.source_page && (
                                <span className="ml-2 text-gray-400">(Pág. {req.evidences[0].source_page})</span>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              {getStatusBadge(req.status)}
                              <Button variant="ghost" size="sm" onClick={() => onEditRequirement(req)} disabled={isTerminal}>
                                <Edit2 size={12} />
                              </Button>
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
        </div>
      )}

      {/* B. Especificaciones por ítem - orphan block */}
      {itemSpecReqs.filter(req => !req.procurement_item_id).length > 0 && (
        <div className="mt-4">
           <h4 className="text-sm font-semibold text-red-600 mb-2">Especificaciones pendientes de asociación</h4>
           <div className="case-requirements__card bg-red-50">
           {itemSpecReqs.filter(req => !req.procurement_item_id).map(req => (
              <div key={req.id} className="flex items-center justify-between py-2 text-sm border-b last:border-0">
                 <div>
                   <span className="font-medium">{req.description}</span>
                   {req.value && <span className="ml-2 text-gray-600">: {req.value}</span>}
                   {req.numeric_value !== null && <span className="ml-2 text-gray-600">: {req.numeric_value} {req.unit}</span>}
                 </div>
                 <div className="flex items-center gap-2">
                   {getStatusBadge(req.status)}
                   <Button variant="ghost" size="sm" onClick={() => onEditRequirement(req)}>
                      <Edit2 size={14} />
                   </Button>
                 </div>
              </div>
           ))}
           </div>
        </div>
      )}

      {/* C. Obligaciones Generales */}
      {renderRequirementTable(
        obligationReqs,
        "Obligaciones Generales",
        "Obligaciones que aplican al proveedor durante la ejecución.",
        [
          { label: "Descripción", render: req => cleanDescription(req.description) },
          { label: "Fuente", render: req => req.evidences?.[0]?.source_document || 'N/A' },
          { label: "Página", render: req => req.evidences?.[0]?.source_page || 'N/A' },
          { label: "Confianza", render: req => req.evidences?.[0]?.confidence !== undefined ? `${(req.evidences[0].confidence * 100).toFixed(0)}%` : 'N/A' },
          { label: "Estado", render: req => getStatusBadge(req.status) }
        ]
      )}

      {/* D. Condiciones Contractuales */}
      {renderRequirementTable(
        contractualReqs,
        "Condiciones Contractuales Normalizadas",
        "Condiciones normalizadas (Plazo, Garantía, Vida Útil, etc.)",
        [
          { label: "Condición", render: req => cleanDescription(req.description) },
          { label: "Valor", render: req => req.numeric_value !== null ? `${req.numeric_value} ${req.unit || ''}` : req.value },
          { label: "Regla", render: req => req.comparator || 'N/A' },
          { label: "Fuente", render: req => req.evidences?.[0]?.source_document || 'N/A' },
          { label: "Página", render: req => req.evidences?.[0]?.source_page || 'N/A' },
          { label: "Confianza", render: req => req.evidences?.[0]?.confidence !== undefined ? `${(req.evidences[0].confidence * 100).toFixed(0)}%` : 'N/A' },
          { label: "Estado", render: req => getStatusBadge(req.status) }
        ]
      )}

      {/* E. Contexto */}
      {contextReqs.length > 0 && (
        <>
          <div className="case-requirements__header-wrapper mt-8">
            <div className="case-requirements__header">
              <h2 className="case-requirements__title">Contexto</h2>
              <p className="case-requirements__subtitle">Información institucional y finalidad (no evaluable).</p>
            </div>
          </div>
          <div className="case-requirements__list mb-6">
            <div className="grid grid-cols-1 gap-4">
              {[...contextReqs].sort((a, b) => {
                const pageA = a.evidences?.[0]?.source_page ?? 0;
                const pageB = b.evidences?.[0]?.source_page ?? 0;
                if (pageA !== pageB) return pageA - pageB;
                return a.id - b.id;
              }).map(req => (
                <div key={req.id} className="case-requirements__card bg-blue-50">
                   <div className="flex justify-between items-start mb-2">
                      <span className="font-semibold text-sm">Contexto</span>
                      <div className="flex items-center gap-2">
                        {getStatusBadge(req.status)}
                        <Button variant="ghost" size="sm" onClick={() => onEditRequirement(req)} disabled={isTerminal}>
                          <Edit2 size={14} />
                        </Button>
                      </div>
                   </div>
                   <p className="text-sm text-gray-700">{cleanDescription(req.description)}</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* F. Requisitos de Selección */}
      {selectionReqs.length > 0 && renderRequirementTable(
        selectionReqs,
        "Requisitos de Selección",
        "Requisitos de habilitación, capacidad técnica o legal del postor.",
        [
          { label: "Descripción", render: req => req.description },
          { label: "Valor", render: req => req.value || 'N/A' },
          { label: "Estado", render: req => getStatusBadge(req.status) }
        ]
      )}
    </div>
  );
};
