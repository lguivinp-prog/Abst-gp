import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import type { Section, CaseStatus } from '../../types';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import './CaseDetail.css';

import { RequirementUpload } from './components/RequirementUpload';
import { ProcessingStatus } from './components/ProcessingStatus';
import { QuotationUpload } from './components/QuotationUpload';
import { OutputGenerator } from './components/OutputGenerator';
import { ComparisonTable } from './components/ComparisonTable';
import { DoublePaneReview } from './components/DoublePaneReview';
import { useComparisonFlow } from './hooks/useComparisonFlow';
import { useCaseDetails } from './hooks/useCaseDetails';
import { casesService } from '../../api/cases.service';
import { AppError } from '../../api/apiError';

const CaseDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [editingSection, setEditingSection] = useState<Section | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { caseData, setCaseData, sections, setSections, loading, error, refresh } = useCaseDetails(id);

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'CREATED': return 'Borrador';
      case 'PROCESSING_REQUIREMENT': return 'Procesando requerimiento';
      case 'REVIEW_SECTIONS': return 'Revisar secciones';
      case 'WAITING_QUOTATION': return 'Esperando cotización';
      case 'COMPARING': return 'Comparando';
      case 'READY_GENERATE': return 'Listo para generar';
      case 'COMPLETED': return 'Completado';
      case 'ERROR': return 'Error';
      default: return status;
    }
  };

  const getStatusBadge = (status: string) => {
    const label = getStatusLabel(status);
    switch (status) {
      case 'CREATED': return <Badge variant="secondary">{label}</Badge>;
      case 'PROCESSING_REQUIREMENT': return <Badge variant="warning">{label}</Badge>;
      case 'REVIEW_SECTIONS': return <Badge variant="warning">{label}</Badge>;
      case 'WAITING_QUOTATION': return <Badge variant="primary">{label}</Badge>;
      case 'COMPARING': return <Badge variant="primary">{label}</Badge>;
      case 'READY_GENERATE': return <Badge variant="primary">{label}</Badge>;
      case 'COMPLETED': return <Badge variant="success">{label}</Badge>;
      case 'ERROR': return <Badge variant="danger">{label}</Badge>;
      default: return <Badge variant="secondary">{label}</Badge>;
    }
  };

  const handleUploadSuccess = (jobId: string) => {
    setActiveJobId(jobId);
    if (caseData) {
      setCaseData({ ...caseData, status: 'PROCESSING_REQUIREMENT' });
    }
  };

  const handleProcessComplete = () => {
    setActiveJobId(null);
    refresh();
  };

  const handleProcessRetry = () => {
    setActiveJobId(null);
    if (caseData && caseData.status === 'PROCESSING_REQUIREMENT') {
      // Si falló el worker, lo devolvemos a CREATED localmente para permitir re-subida
      setCaseData({ ...caseData, status: 'CREATED' });
    }
  };

  const handleComparisonStatusChange = (newStatus: string) => {
    if (caseData) {
      setCaseData({ ...caseData, status: newStatus as CaseStatus });
    }
  };

  const comparisonFlow = useComparisonFlow(id || '', caseData?.status || '', handleComparisonStatusChange);

  const handleEditSection = (section: Section) => {
    setEditingSection(section);
  };

  const handleSaveSection = (updatedSection: Section) => {
    setSections(sections.map(s => s.id === updatedSection.id ? updatedSection : s));
    setEditingSection(null);
  };

  const handleConfirmSections = async () => {
    setActionError(null);
    try {
      if (id) {
        const updatedCase = await casesService.confirmSections(id);
        setCaseData(updatedCase);
      }
    } catch (err) {
      if (err instanceof AppError) {
        setActionError(err.message);
      } else {
        setActionError('Error inesperado al confirmar secciones');
      }
    }
  };

  if (loading && !caseData) {
    return (
      <div className="loading-state h-screen flex flex-col justify-center items-center">
        <div className="spinner"></div>
        <p className="mt-4 text-gray-600">Cargando detalles del expediente...</p>
      </div>
    );
  }

  if (error || !caseData) {
    return (
      <div className="p-6">
        <div className="bg-red-50 text-red-800 p-4 rounded-md border border-red-200">
          <h2 className="font-bold mb-2">Error al cargar el caso</h2>
          <p>{error || 'Expediente no encontrado.'}</p>
          <Button variant="outline" className="mt-4" onClick={() => navigate('/cases')}>
            Volver a Expedientes
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="case-detail-container p-6 max-w-7xl mx-auto">
      <div className="detail-header mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button 
            variant="ghost" 
            leftIcon={<ArrowLeft size={18} />} 
            onClick={() => navigate('/cases')}
          >
            Volver
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold">{caseData.title}</h1>
              {getStatusBadge(caseData.status)}
            </div>
            <p className="text-gray-600">Tipo: {caseData.contract_type.toUpperCase()}</p>
          </div>
        </div>
      </div>

      {actionError && (
        <div className="bg-red-50 text-red-800 p-3 rounded-md mb-6 border border-red-200">
          {actionError}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        {(caseData.status === 'CREATED' || caseData.status === 'draft' || caseData.status === 'ERROR') && !activeJobId ? (
          <div className="flex flex-col gap-4">
            {caseData.status === 'ERROR' && (
              <div className="p-4 bg-red-50 border-l-4 border-red-500 text-red-800 rounded">
                <h3 className="font-bold mb-2">Error al procesar requerimiento</h3>
                {caseData.last_processing_error ? (
                  <pre className="text-sm overflow-auto max-h-32 bg-red-100 p-2 rounded">{caseData.last_processing_error}</pre>
                ) : (
                  <p className="text-sm">Ocurrió un error inesperado al procesar el archivo. Puede reintentar la carga.</p>
                )}
              </div>
            )}
            <RequirementUpload caseId={caseData.id.toString()} onUploadSuccess={handleUploadSuccess} />
          </div>
        ) : (
          <Card>
             <CardHeader><CardTitle>1. Requerimiento</CardTitle></CardHeader>
             <CardContent>
               <Badge variant="success">Completado</Badge>
             </CardContent>
          </Card>
        )}

        {caseData.status === 'PROCESSING_REQUIREMENT' || activeJobId ? (
          <div className="col-span-1 md:col-span-2">
            <ProcessingStatus 
              jobId={activeJobId || ''} 
              onComplete={handleProcessComplete} 
              onRetry={handleProcessRetry}
            />
          </div>
        ) : null}

        {caseData.status === 'COMPARING' || caseData.status === 'READY_GENERATE' || caseData.status === 'COMPLETED' ? (
          <Card>
             <CardHeader><CardTitle>2. Cotización</CardTitle></CardHeader>
             <CardContent><Badge variant="success">Cotización Procesada</Badge></CardContent>
          </Card>
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
      </div>

      {(caseData.status === 'COMPARING' || caseData.status === 'READY_GENERATE' || caseData.status === 'COMPLETED') && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Inteligencia Documental: Comparación</CardTitle>
          </CardHeader>
          <CardContent>
            {comparisonFlow.status === 'idle' && (
              <div className="text-center p-6 bg-gray-50 rounded-lg">
                <p className="text-gray-600 mb-4">La cotización ha sido procesada. Listo para comparar condiciones.</p>
                <Button 
                  onClick={comparisonFlow.executeComparison} 
                  disabled={comparisonFlow.isExecuting}
                >
                  Ejecutar Comparación
                </Button>
              </div>
            )}

            {comparisonFlow.status === 'running' && (
              <div className="flex flex-col justify-center items-center p-8 bg-blue-50 text-blue-800 rounded-lg">
                <div className="spinner mb-4 border-blue-500"></div>
                <p className="font-semibold">Comparando condiciones...</p>
                <p className="text-sm mt-2 opacity-80">Por favor espere, esto puede tomar unos segundos.</p>
              </div>
            )}

            {comparisonFlow.status === 'uncertain' && (
              <div className="bg-yellow-50 text-yellow-800 p-4 rounded-md border border-yellow-200">
                <p className="font-medium mb-2">Se perdió la comunicación durante la comparación.</p>
                <p className="text-sm">El servidor podría haber completado la operación. Verificaremos el estado del expediente antes de permitir otro intento.</p>
                <Button variant="outline" size="sm" className="mt-4" onClick={() => { refresh(); comparisonFlow.refreshResults(); }}>
                  Verificar Estado
                </Button>
              </div>
            )}

            {comparisonFlow.error && comparisonFlow.status !== 'uncertain' && (
              <div className="bg-red-50 text-red-800 p-4 rounded-md border border-red-200 mt-4">
                <h3 className="font-bold mb-2">Error en la comparación</h3>
                <p>{comparisonFlow.error.message}</p>
                <Button variant="outline" size="sm" className="mt-4" onClick={comparisonFlow.executeComparison}>
                  Reintentar
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {comparisonFlow.status === 'completed' && comparisonFlow.comparisons.length > 0 && (
        <div className="mt-6">
          <ComparisonTable comparisons={comparisonFlow.comparisons} />
        </div>
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
  );
};

export default CaseDetail;
