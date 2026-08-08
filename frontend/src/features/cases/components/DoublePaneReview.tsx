import React from 'react';
import type { Section } from '../../../types';
import { useRequirementDocument } from '../hooks/useRequirementDocument';
import { SectionSelector } from './SectionSelector';
import { SectionEditor } from './SectionEditor';
import { Button } from '../../../components/ui/Button';
import { AlertCircle, Download, FileText, RefreshCw } from 'lucide-react';

interface DoublePaneReviewProps {
  caseId: string;
  sections: Section[];
  onEditSection: (section: Section) => void;
  onSaveSection: (section: Section) => void;
  onConfirmSections: () => void;
  editingSection: Section | null;
  onCancelEdit: () => void;
}

export const DoublePaneReview: React.FC<DoublePaneReviewProps> = ({
  caseId,
  sections,
  onEditSection,
  onSaveSection,
  onConfirmSections,
  editingSection,
  onCancelEdit
}) => {
  const { blobUrl, isLoading, error, isNotAvailable, retry } = useRequirementDocument(caseId);

  const handleDownload = () => {
    if (blobUrl) {
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `requirement-${caseId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }
  };

  return (
    <div className="flex flex-col lg:flex-row gap-6 mt-6 min-h-[600px] items-stretch">
      {/* Left Pane: PDF Viewer */}
      <div className="w-full lg:w-1/2 flex flex-col border border-gray-200 rounded-lg bg-white overflow-hidden shadow-sm h-[800px]">
        <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <FileText className="text-gray-500" size={18} />
            <h3 className="font-semibold text-gray-700">Documento Original</h3>
          </div>
          {blobUrl && (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => window.open(blobUrl, '_blank')}>
                Abrir Pestaña
              </Button>
              <Button variant="ghost" size="sm" onClick={handleDownload} leftIcon={<Download size={16} />}>
                Descargar
              </Button>
            </div>
          )}
        </div>
        
        <div className="flex-1 bg-gray-100 relative flex items-center justify-center p-4">
          {isLoading && (
            <div className="flex flex-col items-center justify-center text-gray-500">
              <div className="spinner mb-4 border-t-primary w-8 h-8 rounded-full border-4 border-gray-300 animate-spin"></div>
              <p>Cargando documento seguro...</p>
              <p className="text-sm mt-2 text-center max-w-xs">Los documentos grandes pueden tardar unos momentos en descargarse a la memoria.</p>
            </div>
          )}

          {error && !isLoading && (
            <div className="flex flex-col items-center text-red-600 bg-red-50 p-6 rounded-lg max-w-md text-center border border-red-200">
              <AlertCircle size={32} className="mb-3" />
              <h4 className="font-bold mb-1">Error de conexión</h4>
              <p className="text-sm mb-4">{error.message || 'No se pudo cargar el documento.'}</p>
              <Button onClick={retry} variant="outline" leftIcon={<RefreshCw size={16} />}>Reintentar</Button>
            </div>
          )}

          {isNotAvailable && !isLoading && (
            <div className="flex flex-col items-center text-gray-600 bg-white p-6 rounded-lg shadow-sm border border-gray-200 max-w-md text-center">
              <FileText size={32} className="mb-3 text-gray-400" />
              <h4 className="font-bold mb-1">Documento no disponible</h4>
              <p className="text-sm">El archivo físico del requerimiento original no se encuentra disponible en el almacenamiento.</p>
            </div>
          )}

          {blobUrl && !isLoading && (
            <object
              data={blobUrl}
              type="application/pdf"
              className="w-full h-full"
            >
              <div className="flex flex-col items-center justify-center h-full text-gray-600 bg-white p-6 text-center">
                <AlertCircle size={32} className="mb-3 text-yellow-500" />
                <h4 className="font-bold mb-2">El navegador no pudo mostrar este documento.</h4>
                <p className="text-sm mb-4">Tu navegador no tiene un visor de PDF integrado o está bloqueando la previsualización.</p>
                <div className="flex gap-3">
                  <Button onClick={() => window.open(blobUrl, '_blank')} variant="outline">
                    Abrir en nueva pestaña
                  </Button>
                  <Button onClick={handleDownload} variant="primary">
                    Descargar para continuar la revisión
                  </Button>
                </div>
              </div>
            </object>
          )}
        </div>
      </div>

      {/* Right Pane: Section Review */}
      <div className="w-full lg:w-1/2 flex flex-col h-[800px]">
        {editingSection ? (
          <div className="h-full overflow-hidden bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col">
            <SectionEditor
              section={editingSection}
              onSave={onSaveSection}
              onCancel={onCancelEdit}
            />
          </div>
        ) : (
          <div className="h-full overflow-hidden bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col">
            <SectionSelector
              sections={sections}
              onEditSection={onEditSection}
              onContinue={onConfirmSections}
            />
          </div>
        )}
      </div>
    </div>
  );
};
