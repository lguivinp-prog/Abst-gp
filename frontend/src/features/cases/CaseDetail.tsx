import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import apiClient from '../../api/client';
import type { Case, Section, ComparisonResult } from '../../types';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Card, CardHeader, CardTitle, CardContent } from '../../components/ui/Card';
import './CaseDetail.css';

import { RequirementUpload } from './components/RequirementUpload';
import { ProcessingStatus } from './components/ProcessingStatus';
import { SectionSelector } from './components/SectionSelector';
import { SectionEditor } from './components/SectionEditor';
import { QuotationUpload } from './components/QuotationUpload';
import { OutputGenerator } from './components/OutputGenerator';
import { ComparisonTable } from './components/ComparisonTable';

const CaseDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  // Current active job id (if any)
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [comparisons, setComparisons] = useState<ComparisonResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingSection, setEditingSection] = useState<Section | null>(null);

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

  useEffect(() => {
    if (id) {
      fetchCaseDetails(id);
    }
  }, [id]);

  const fetchCaseDetails = async (caseId: string) => {
    setLoading(true);
    try {
      const [caseRes, sectionsRes, comparisonsRes] = await Promise.all([
        apiClient.get(`/cases/${caseId}`),
        apiClient.get(`/cases/${caseId}/sections`).catch(() => ({ data: [] })),
        apiClient.get(`/cases/${caseId}/comparison`).catch(() => ({ data: [] }))
      ]);
      setCaseData(caseRes.data);
      setSections(sectionsRes.data);
      setComparisons(comparisonsRes.data);
    } catch (error) {
      console.error('Error fetching case details:', error);
    } finally {
      setLoading(false);
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
    fetchCaseDetails(id!);
  };

  const handleEditSection = (section: Section) => {
    setEditingSection(section);
  };

  const handleSaveSection = (updatedSection: Section) => {
    setSections(sections.map(s => s.id === updatedSection.id ? updatedSection : s));
    setEditingSection(null);
  };

  const handleConfirmSections = async () => {
    try {
      const res = await apiClient.post(`/cases/${id}/sections/confirm`);
      setCaseData(res.data);
    } catch (error) {
      console.error('Error confirming sections:', error);
      alert('Error al confirmar secciones');
    }
  };

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner"></div>
        <p>Cargando detalles del expediente...</p>
      </div>
    );
  }

  if (!caseData) {
    return <div>Expediente no encontrado.</div>;
  }

  return (
    <div className="case-detail-container p-6">
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
            <ProcessingStatus jobId={activeJobId || ''} onComplete={handleProcessComplete} />
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
            onUploadSuccess={() => fetchCaseDetails(id!)} 
            disabled={caseData.status !== 'WAITING_QUOTATION'} 
          />
        ))}

        {caseData.status !== 'CREATED' && caseData.status !== 'draft' && caseData.status !== 'PROCESSING_REQUIREMENT' && !activeJobId && (
          <OutputGenerator 
            caseId={caseData.id.toString()}
            caseStatus={caseData.status}
            disabled={caseData.status !== 'COMPARING' && caseData.status !== 'READY_GENERATE' && caseData.status !== 'COMPLETED'}
            onGenerateSuccess={() => fetchCaseDetails(id!)}
          />
        )}
      </div>

      {(caseData.status === 'READY_GENERATE' || caseData.status === 'COMPLETED') && comparisons.length > 0 && (
        <ComparisonTable comparisons={comparisons} />
      )}

      {sections.length > 0 && !activeJobId && caseData.status === 'REVIEW_SECTIONS' && (
        <SectionSelector 
          sections={sections} 
          onEditSection={handleEditSection} 
          onContinue={handleConfirmSections} 
        />
      )}

      {editingSection && (
        <SectionEditor 
          section={editingSection} 
          onSave={handleSaveSection} 
          onCancel={() => setEditingSection(null)} 
        />
      )}
    </div>
  );
};

export default CaseDetail;
