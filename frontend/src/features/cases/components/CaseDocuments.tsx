import React, { useEffect, useState } from 'react';
import { Clock, CheckCircle, FileText } from 'lucide-react';
import { documentsService } from '../../../api/v6/documents.service';
import { requirementsService } from '../../../api/v6/requirements.service';
import type { DocumentResponse } from '../../../api/v6/documents.types';
import { AppError } from '../../../api/apiError';
import { RequirementUpload } from './RequirementUpload';

interface CaseDocumentsProps {
  caseId: string;
}

export const CaseDocuments: React.FC<CaseDocumentsProps> = ({ caseId }) => {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [extractingId, setExtractingId] = useState<number | null>(null);
  const [extractMessage, setExtractMessage] = useState<{ id: number; type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    let mounted = true;

    const fetchDocuments = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await documentsService.getDocuments(caseId);
        if (mounted) {
          setDocuments(data);
        }
      } catch (err) {
        if (mounted) {
          if (err instanceof AppError) {
            setError(err.message);
          } else {
            setError('Error inesperado al cargar documentos.');
          }
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    fetchDocuments();
    return () => { mounted = false; };
  }, [caseId]);

  const handleExtract = async (docId: number) => {
    if (extractingId !== null) return;

    setExtractingId(docId);
    setExtractMessage(null);
    try {
      await requirementsService.extractRequirements(caseId, docId);
      setExtractMessage({ id: docId, type: 'success', text: 'Requerimientos extraídos/verificados. (Revisa la pestaña Requerimientos)' });
    } catch (err) {
      if (err instanceof AppError) {
        setExtractMessage({ id: docId, type: 'error', text: err.message });
      } else {
        setExtractMessage({ id: docId, type: 'error', text: 'Error inesperado al extraer requerimientos.' });
      }
    } finally {
      setExtractingId(null);
    }
  };

  if (loading) {
    return (
      <div className="case-documents__loading">
        <div className="spinner"></div>
        <p>Cargando documentos...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="case-documents__error">
        <p>{error}</p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="case-documents__empty">
        <div className="mb-4">
          <p>No hay documentos registrados para este expediente.</p>
        </div>
        <div className="max-w-lg mx-auto">
          <RequirementUpload 
            caseId={caseId} 
            onUploadSuccess={() => {
              // Reload page or re-fetch documents?
              // The component will re-fetch if we just reset some state or we can just reload for now
              window.location.reload();
            }} 
          />
        </div>
      </div>
    );
  }

  return (
    <div className="case-documents">
      <div className="case-documents__header">
        <h2 className="case-documents__title">Documentos del Expediente</h2>
      </div>

      <div className="case-documents__list">
        {documents.map((doc) => (
          <div key={doc.id} className="case-documents__item">
            <div className="case-documents__icon-wrapper">
              <FileText size={24} />
            </div>

            <div className="case-documents__info">
              <h3 className="case-documents__filename" title={doc.original_filename}>
                {doc.original_filename}
              </h3>

              <div className="case-documents__meta">
                {doc.created_at && (
                  <span className="case-documents__date">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </span>
                )}

                {doc.processing_status && (
                  <span className="case-documents__status-badge">
                    {doc.processing_status}
                  </span>
                )}
              </div>
            </div>

            <div className="case-documents__actions-col">
              <div className="case-documents__status">
                {doc.extraction_ready ? (
                  <div className="case-documents__status-ready">
                    <CheckCircle size={16} />
                    <span>Listo para análisis</span>
                  </div>
                ) : (
                  <div className="case-documents__status-pending">
                    <Clock size={16} />
                    <span>Procesamiento pendiente</span>
                  </div>
                )}
              </div>

              <div className="case-documents__actions-row" style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '8px' }}>
                <button
                  className="case-documents__extract-btn"
                  style={{ backgroundColor: '#f3f4f6', color: '#374151', border: '1px solid #d1d5db' }}
                  onClick={async () => {
                    try {
                      const blob = await documentsService.getDocumentContent(caseId, doc.id);
                      const url = URL.createObjectURL(blob);
                      window.open(url, '_blank');
                    } catch (err) {
                      alert('Error al abrir el PDF');
                    }
                  }}
                >
                  Ver PDF
                </button>

                {doc.extraction_ready && (
                  <div className="case-documents__extract-action" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <button
                      className="case-documents__extract-btn"
                      onClick={() => handleExtract(doc.id)}
                      disabled={extractingId !== null}
                    >
                      {extractingId === doc.id ? 'Extrayendo...' : 'Extraer requerimientos'}
                    </button>
                    {extractMessage?.id === doc.id && (
                      <div className={`case-documents__extract-msg case-documents__extract-msg--${extractMessage.type}`}>
                        {extractMessage.text}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
