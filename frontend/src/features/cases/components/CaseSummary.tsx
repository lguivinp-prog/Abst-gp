import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import type { Case } from '../../../types';
import { FileText, Tag, Calendar, Activity, AlertCircle } from 'lucide-react';

interface CaseSummaryProps {
  caseData: Case;
}

export const CaseSummary: React.FC<CaseSummaryProps> = ({ caseData }) => {
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
            <div className="text-2xl font-bold">{caseData.status}</div>
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
        <p className="text-sm text-gray-500">Navegue por las pestañas superiores para ver requerimientos, evaluar cotizaciones y realizar validaciones.</p>
      </div>
    </div>
  );
};
