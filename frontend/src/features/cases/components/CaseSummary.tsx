import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { RequirementUpload } from './RequirementUpload';
import { ProcessingStatus } from './ProcessingStatus';
import { QuotationUpload } from './QuotationUpload';
import { OutputGenerator } from './OutputGenerator';
import { ComparisonTable } from './ComparisonTable';
import { DoublePaneReview } from './DoublePaneReview';
import type { Section, Case } from '../../../types';
import { FileText, Tag, Calendar } from 'lucide-react';
import { useComparisonFlow } from '../hooks/useComparisonFlow';

interface CaseSummaryProps {
  caseData: Case;
  activeJobId: string | null;
  sections: Section[];
  editingSection: Section | null;
  comparisonFlow: ReturnType<typeof useComparisonFlow>;
  handleUploadSuccess: (jobId: string) => void;
  handleProcessComplete: () => void;
  handleProcessRetry: () => void;
  refresh: () => void;
  handleEditSection: (section: Section) => void;
  handleSaveSection: (section: Section) => void;
  handleConfirmSections: () => void;
  setEditingSection: (section: Section | null) => void;
}

export const CaseSummary: React.FC<CaseSummaryProps> = ({
  caseData,
  activeJobId,
  sections,
  editingSection,
  comparisonFlow,
  handleUploadSuccess,
  handleProcessComplete,
  handleProcessRetry,
  refresh,
  handleEditSection,
  handleSaveSection,
  handleConfirmSections,
  setEditingSection
}) => {

  const formatDate = (dateString?: string) => {
    if (!dateString) return null;
    try {
      const d = new Date(dateString);
      return d.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch (e) {
      return null;
    }
  };

  const creationDate = formatDate(caseData.created_at);

  return (
    <div className="case-summary-container">
      <div className="case-summary__header">
        <h2 className="case-summary__title">Resumen del Expediente</h2>
        <p className="case-summary__subtitle">Vista general del estado y avance del expediente de contratación.</p>
      </div>

      {/* Info General Row */}
      <div className="case-summary__grid-row">
        <div className="case-summary__info-card">
          <div className="case-summary__info-icon-wrapper">
            <FileText size={20} />
          </div>
          <div>
            <p className="case-summary__info-label">Código / Título</p>
            <p className="case-summary__info-value">{caseData.title}</p>
          </div>
        </div>

        <div className="case-summary__info-card">
          <div className="case-summary__info-icon-wrapper">
            <Tag size={20} />
          </div>
          <div>
            <p className="case-summary__info-label">Tipo de contratación</p>
            <p className="case-summary__info-value">{caseData.contract_type.toUpperCase()}</p>
          </div>
        </div>

        {creationDate && (
          <div className="case-summary__info-card">
            <div className="case-summary__info-icon-wrapper">
              <Calendar size={20} />
            </div>
            <div>
              <p className="case-summary__info-label">Fecha de creación</p>
              <p className="case-summary__info-value">{creationDate}</p>
            </div>
          </div>
        )}
      </div>

      <div className="case-summary__modules-grid">
        {(caseData.status === 'CREATED' || caseData.status === 'draft' || caseData.status === 'ERROR') && !activeJobId ? (
          <div className="case-summary__module-card case-summary__module-card--flex">
            {caseData.status === 'ERROR' && (
              <div className="case-summary__error-box">
                <h3 className="case-summary__error-title">Error al procesar requerimiento</h3>
                {caseData.last_processing_error ? (
                  <pre className="case-summary__error-pre">{caseData.last_processing_error}</pre>
                ) : (
                  <p className="case-summary__error-text">Ocurrió un error inesperado al procesar el archivo. Puede reintentar la carga.</p>
                )}
              </div>
            )}
            <h3 className="case-summary__module-title">
               <span className="case-summary__number-badge case-summary__number-badge--blue">1</span>
               Requerimiento
            </h3>
            <RequirementUpload caseId={caseData.id.toString()} onUploadSuccess={handleUploadSuccess} />
          </div>
        ) : (
          <div className="case-summary__module-card">
            <div className="case-summary__module-header-row">
              <h3 className="case-summary__module-title-no-margin">
                <span className="case-summary__number-badge case-summary__number-badge--green">✓</span>
                1. Requerimiento
              </h3>
              <Badge variant="success">COMPLETADO</Badge>
            </div>
            <p className="case-summary__module-desc">El requerimiento ha sido registrado y validado correctamente.</p>
          </div>
        )}

        {caseData.status === 'PROCESSING_REQUIREMENT' || activeJobId ? (
          <div className="case-summary__module-card">
            <ProcessingStatus
              jobId={activeJobId || ''}
              onComplete={handleProcessComplete}
              onRetry={handleProcessRetry}
            />
          </div>
        ) : null}

        {caseData.status === 'COMPARING' || caseData.status === 'READY_GENERATE' || caseData.status === 'COMPLETED' ? (
          <div className="case-summary__module-card">
            <div className="case-summary__module-header-row">
              <h3 className="case-summary__module-title-no-margin">
                <span className="case-summary__number-badge case-summary__number-badge--blue">2</span>
                2. Cotización
              </h3>
              <Badge variant="success">PROCESADA</Badge>
            </div>
            <p className="case-summary__module-desc">Suba cotización del proveedor para extraer condiciones.</p>
          </div>
        ) : (caseData.status !== 'CREATED' && caseData.status !== 'draft' && caseData.status !== 'PROCESSING_REQUIREMENT' && !activeJobId && (
          <QuotationUpload
            caseId={caseData.id.toString()}
            onUploadSuccess={refresh}
            disabled={caseData.status !== 'WAITING_QUOTATION'}
          />
        ))}

        {caseData.status !== 'CREATED' && caseData.status !== 'draft' && caseData.status !== 'PROCESSING_REQUIREMENT' && !activeJobId && (
          <OutputGenerator
            caseId={caseData.id.toString()}
            caseStatus={caseData.status}
            disabled={caseData.status !== 'READY_GENERATE' && caseData.status !== 'COMPLETED' || comparisonFlow.status !== 'completed' || comparisonFlow.comparisons.length === 0}
            onGenerateSuccess={refresh}
          />
        )}

        {caseData.status === 'REVIEW_SECTIONS' && !activeJobId && (
          <DoublePaneReview
            caseId={caseData.id.toString()}
            sections={sections}
            onEditSection={handleEditSection}
            onSaveSection={handleSaveSection}
            onConfirmSections={handleConfirmSections}
            editingSection={editingSection}
            onCancelEdit={() => setEditingSection(null)}
          />
        )}
      </div>

      {(caseData.status === 'COMPARING' || caseData.status === 'READY_GENERATE' || caseData.status === 'COMPLETED') && (
        <Card className="case-summary__comparison-card">
          <CardHeader>
            <CardTitle className="case-summary__comparison-card-title">Inteligencia Documental: Comparación</CardTitle>
          </CardHeader>
          <CardContent>
            {comparisonFlow.status === 'idle' && (
              <div className="case-summary__comparison-idle">
                <p>La cotización ha sido procesada. Listo para comparar condiciones.</p>
                <Button
                  onClick={comparisonFlow.executeComparison}
                  disabled={comparisonFlow.isExecuting}
                >
                  Ejecutar Comparación
                </Button>
              </div>
            )}

            {comparisonFlow.status === 'running' && (
              <div className="case-summary__comparison-running">
                <div className="spinner"></div>
                <p className="font-semibold">Comparando condiciones...</p>
                <p className="text-sm">Por favor espere, esto puede tomar unos segundos.</p>
              </div>
            )}

            {comparisonFlow.status === 'uncertain' && (
              <div className="case-summary__comparison-uncertain">
                <p className="font-medium">Se perdió la comunicación durante la comparación.</p>
                <p className="text-sm">El servidor podría haber completado la operación. Verificaremos el estado del expediente antes de permitir otro intento.</p>
                <Button variant="outline" size="sm" className="btn-mt-4" onClick={() => { refresh(); comparisonFlow.refreshResults(); }}>
                  Verificar Estado
                </Button>
              </div>
            )}

            {comparisonFlow.error && comparisonFlow.status !== 'uncertain' && (
              <div className="case-summary__comparison-error">
                <h3>Error en la comparación</h3>
                <p>{comparisonFlow.error.message}</p>
                <Button variant="outline" size="sm" className="btn-mt-4" onClick={comparisonFlow.executeComparison}>
                  Reintentar
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {comparisonFlow.status === 'completed' && comparisonFlow.comparisons.length > 0 && (
        <div className="case-summary__comparison-table-wrapper">
          <ComparisonTable comparisons={comparisonFlow.comparisons} />
        </div>
      )}
    </div>
  );
};
