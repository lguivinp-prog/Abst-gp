import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import type { Case } from '../../../types';
import { FileText, Tag, Calendar, Activity, AlertCircle, UploadCloud, ArrowRight } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { useRequirementDocument } from '../hooks/useRequirementDocument';

interface CaseSummaryProps {
  caseData: Case;
  onNavigate?: (tab: string) => void;
}

export const CaseSummary: React.FC<CaseSummaryProps> = ({ caseData, onNavigate }) => {
  const formatDate = (dateString?: string) => {
    if (!dateString) return null;
    try {
      const d = new Date(dateString);
      return d.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch (e) {
      return null;
    }
  };

  const { blobUrl, isLoading, isNotAvailable } = useRequirementDocument(caseData.id?.toString());
  const creationDate = formatDate(caseData.created_at);

  return (
    <div className="case-summary-container">
      <div className="case-summary__header">
        <h2 className="case-summary__title">Resumen del Expediente</h2>
        <p className="case-summary__subtitle">Vista general del estado y avance del expediente de contratación (V6 Dashboard).</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Código / Título</CardTitle>
            <FileText size={16} className="text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{caseData.title}</div>
            <p className="text-xs text-muted-foreground mt-1">Expediente ID: {caseData.id}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Tipo</CardTitle>
            <Tag size={16} className="text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{caseData.contract_type.toUpperCase()}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Estado</CardTitle>
            <Activity size={16} className="text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {(caseData.status as string) === 'CREATED' ? 'CREADO' : (caseData.status as string) === 'PENDING' ? 'PENDIENTE' : (caseData.status as string) === 'APPROVED' ? 'APROBADA' : (caseData.status as string) === 'OBSERVED' ? 'OBSERVADA' : (caseData.status as string) === 'REJECTED' ? 'RECHAZADA' : caseData.status}
            </div>
          </CardContent>
        </Card>

        {creationDate && (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Fecha de Creación</CardTitle>
              <Calendar size={16} className="text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{creationDate}</div>
            </CardContent>
          </Card>
        )}
      </div>

      {caseData.status === 'ERROR' && caseData.last_processing_error && (
        <div className="mt-6 bg-red-50 border-l-4 border-red-500 p-4 rounded-md">
          <div className="flex">
            <div className="flex-shrink-0">
              <AlertCircle className="h-5 w-5 text-red-400" />
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error en el expediente</h3>
              <div className="mt-2 text-sm text-red-700">
                <p>{caseData.last_processing_error}</p>
              </div>
            </div>
          </div>
        </div>
      )}
      
      <div className="mt-8">
        <h3 className="text-lg font-medium mb-4">Información Adicional</h3>
        <p className="text-sm text-gray-500 mb-6">Navegue por las pestañas superiores para ver requerimientos, evaluar cotizaciones y realizar validaciones.</p>
        
        {!isLoading && (
          <div className="flex items-center p-4 bg-blue-50 border border-blue-200 rounded-md shadow-sm w-full md:w-1/2">
            {isNotAvailable ? (
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-blue-800">Requerimiento no cargado</h4>
                <p className="text-sm text-blue-600 mt-1">Este expediente aún no tiene un documento de requerimiento asociado.</p>
              </div>
            ) : blobUrl ? (
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-green-800">Requerimiento procesado</h4>
                <p className="text-sm text-green-600 mt-1">El documento ha sido cargado y está listo para revisión.</p>
              </div>
            ) : null}
            
            <div className="ml-4">
              {(isNotAvailable || !blobUrl) ? (
                <Button onClick={() => onNavigate && onNavigate('documentos')} className="flex items-center gap-2">
                  <UploadCloud size={16} /> Cargar requerimiento
                </Button>
              ) : (
                <Button onClick={() => onNavigate && onNavigate('requerimiento')} className="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white">
                  <ArrowRight size={16} /> Revisar requerimiento
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
