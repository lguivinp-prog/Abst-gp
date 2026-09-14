import React, { useEffect, useState } from 'react';
import { Clock, CheckCircle, FileText } from 'lucide-react';
import { documentsService } from '../../../api/v6/documents.service';
import type { DocumentResponse } from '../../../api/v6/documents.types';
import { AppError } from '../../../api/apiError';

interface CaseDocumentsProps {
  caseId: string;
}

export const CaseDocuments: React.FC<CaseDocumentsProps> = ({ caseId }) => {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        <p>No hay documentos registrados para este expediente.</p>
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
          </div>
        ))}
      </div>
    </div>
  );
};
