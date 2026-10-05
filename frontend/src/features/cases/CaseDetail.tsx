// @ts-nocheck
import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, FileText } from 'lucide-react';
import type { Section, CaseStatus } from '../../types';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { CaseWorkspaceNav } from './components/CaseWorkspaceNav';
import { CaseSummary } from './components/CaseSummary';
import { CaseRequirements } from './components/CaseRequirements';
import { CaseDocuments } from './components/CaseDocuments';
import { CaseSuppliers } from './components/CaseSuppliers';
import { CaseOffers } from './components/CaseOffers';
import { CaseValidations } from './components/CaseValidations';
import { CaseEvaluations } from './components/CaseEvaluations';
import { CaseSelection } from './components/CaseSelection';
import { CaseResult } from './components/CaseResult';
import { CaseHistory } from './components/CaseHistory';
import { CaseAssistant } from './components/CaseAssistant';
import { useComparisonFlow } from './hooks/useComparisonFlow';
import { useCaseDetails } from './hooks/useCaseDetails';
import { casesService } from '../../api/cases.service';
import { AppError } from '../../api/apiError';
import './CaseWorkspace.css';

const CaseDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState('resumen');
  const [_activeJobId, setActiveJobId] = useState<string | null>(null);
  const [_editingSection, setEditingSection] = useState<Section | null>(null);
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

  const _handleUploadSuccess = (jobId: string) => {
    setActiveJobId(jobId);
    if (caseData) {
      setCaseData({ ...caseData, status: 'PROCESSING_REQUIREMENT' });
    }
  };

  const _handleProcessComplete = () => {
    setActiveJobId(null);
    refresh();
  };

  const _handleProcessRetry = () => {
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

  const _comparisonFlow = useComparisonFlow(id || '', caseData?.status || '', handleComparisonStatusChange);

  const _handleEditSection = (section: Section) => {
    setEditingSection(section);
  };

  const _handleSaveSection = (updatedSection: Section) => {
    setSections(sections.map(s => s.id === updatedSection.id ? updatedSection : s));
    setEditingSection(null);
  };

  const _handleConfirmSections = async () => {
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
      <div className="case-detail-page__loading h-screen">
        <div className="spinner"></div>
        <p className="case-detail-page__loading-text">Cargando detalles del expediente...</p>
      </div>
    );
  }

  if (error || !caseData) {
    return (
      <div className="case-detail-page__error-container">
        <div className="case-detail-page__error-card">
          <h2 className="case-detail-page__error-title">Error al cargar el caso</h2>
          <p>{error || 'Expediente no encontrado.'}</p>
          <Button variant="outline" className="case-detail-page__error-btn" onClick={() => navigate('/expedientes')}>
            Volver a Expedientes
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="case-detail-page">
      <div className="case-detail-container">
        <div className="detail-header">
          <Button
            variant="ghost"
            leftIcon={<ArrowLeft size={18} />}
            onClick={() => navigate('/expedientes')}
            className="case-detail-back"
          >
            Volver a expedientes
          </Button>

          <div className="case-detail-header-card">
            <div className="case-detail-header-info">
              <div className="case-detail-icon">
                <FileText size={32} />
              </div>
              <div>
                <h1 className="case-detail-title">{caseData.title}</h1>
                <div className="case-detail-meta">
                  <Badge variant="secondary" className="case-detail-type-badge">
                    Tipo: {caseData.contract_type.toUpperCase()}
                  </Badge>
                </div>
              </div>
            </div>
            <div className="case-detail-status-container">
              {getStatusBadge(caseData.status)}
              {actionError && (
                <div className="case-detail-error-msg">{actionError}</div>
              )}
            </div>
          </div>
        </div>

        <CaseWorkspaceNav activeTab={activeTab} onTabChange={setActiveTab} />

        <div className="v6-workspace-content">
          {activeTab === 'resumen' ? (
            <CaseSummary caseData={caseData} onNavigate={(tab) => setActiveTab(tab)} />
          ) : activeTab === 'requerimiento' ? (
            <CaseRequirements 
              caseId={id || ''} 
              caseStatus={caseData?.status} 
              onRefresh={refresh} 
            />
          ) : activeTab === 'documentos' ? (
            <CaseDocuments caseId={id || ''} onRefresh={refresh} />
          ) : activeTab === 'proveedores' ? (
            <CaseSuppliers caseId={id || ''} />
          ) : activeTab === 'ofertas' ? (
            <CaseOffers caseId={id || ''} />
          ) : activeTab === 'validaciones' ? (
            <CaseValidations caseId={id || ''} />
          ) : activeTab === 'evaluacion' ? (
            <CaseEvaluations caseId={id || ''} />
          ) : activeTab === 'seleccion' ? (
            <CaseSelection caseId={id || ''} />
          ) : activeTab === 'resultado' ? (
            <CaseResult caseId={id || ''} />
          ) : activeTab === 'historial' ? (
            <CaseHistory caseId={id || ''} />
          ) : activeTab === 'ia' ? (
            <CaseAssistant caseId={id || ''} />
          ) : (
            <div className="case-detail-placeholder">
              <p className="case-detail-placeholder-text">
                Módulo preparado para la arquitectura V6.<br />
                La integración funcional se incorporará en la siguiente fase.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CaseDetail;
