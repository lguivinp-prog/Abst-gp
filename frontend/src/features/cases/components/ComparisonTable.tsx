import React, { useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import type { ConditionComparison, MatchStatus } from '../domain/models';

interface ComparisonTableProps {
  comparisons: ConditionComparison[];
}

export const ComparisonTable: React.FC<ComparisonTableProps> = ({ comparisons }) => {
  if (!comparisons || comparisons.length === 0) return null;

  const hasConfidence = comparisons.some(c => c.confidenceScore !== null);
  const hasEvidence = comparisons.some(c => c.evidencePage !== null);

  const summary = useMemo(() => {
    let match = 0;
    let mismatch = 0;
    let manual_review = 0;
    let not_found = 0;
    
    comparisons.forEach(c => {
      if (c.status === 'match') match++;
      else if (c.status === 'mismatch') mismatch++;
      else if (c.status === 'manual_review') manual_review++;
      else if (c.status === 'not_found') not_found++;
    });

    return { total: comparisons.length, match, mismatch, manual_review, not_found };
  }, [comparisons]);

  const requiresHumanReview = summary.manual_review > 0 || summary.not_found > 0;

  const getStatusBadge = (status: MatchStatus) => {
    switch (status) {
      case 'match':
        return <Badge variant="success">Cumple</Badge>;
      case 'mismatch':
        return <Badge variant="danger">No cumple</Badge>;
      case 'manual_review':
        return <Badge variant="warning">Revisión requerida</Badge>;
      case 'not_found':
        return <Badge variant="secondary">No encontrado</Badge>;
      default:
        return <Badge variant="secondary">Desconocido</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Resumen */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Resumen de Comparación</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
            <div className="p-3 bg-gray-50 rounded-lg text-center">
              <p className="text-sm text-gray-500">Total</p>
              <p className="text-xl font-bold">{summary.total}</p>
            </div>
            <div className="p-3 bg-green-50 rounded-lg text-center">
              <p className="text-sm text-green-700">Cumplen</p>
              <p className="text-xl font-bold text-green-700">{summary.match}</p>
            </div>
            <div className="p-3 bg-red-50 rounded-lg text-center">
              <p className="text-sm text-red-700">No Cumplen</p>
              <p className="text-xl font-bold text-red-700">{summary.mismatch}</p>
            </div>
            <div className="p-3 bg-yellow-50 rounded-lg text-center">
              <p className="text-sm text-yellow-700">Revisión Req.</p>
              <p className="text-xl font-bold text-yellow-700">{summary.manual_review}</p>
            </div>
            <div className="p-3 bg-gray-100 rounded-lg text-center">
              <p className="text-sm text-gray-600">No Encontrado</p>
              <p className="text-xl font-bold text-gray-600">{summary.not_found}</p>
            </div>
          </div>
          
          {requiresHumanReview && (
            <div className="p-4 bg-yellow-50 text-yellow-800 rounded-md border border-yellow-200">
              <p className="font-medium">Existen condiciones que requieren revisión humana antes de generar el documento final.</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tabla */}
      <Card>
        <CardHeader>
          <CardTitle>Resultados Detallados</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm text-left text-gray-500">
              <thead className="text-xs text-gray-700 uppercase bg-gray-50">
                <tr>
                  <th className="px-6 py-3">Condición</th>
                  <th className="px-6 py-3">Requerimiento</th>
                  <th className="px-6 py-3">Cotización</th>
                  <th className="px-6 py-3">Valor Final</th>
                  <th className="px-6 py-3">Estado</th>
                  {hasConfidence && <th className="px-6 py-3">Confianza</th>}
                  {hasEvidence && <th className="px-6 py-3">Evidencia</th>}
                </tr>
              </thead>
              <tbody>
                {comparisons.map((comp) => (
                  <tr key={comp.id} className="bg-white border-b">
                    <td className="px-6 py-4 font-medium text-gray-900">{comp.fieldName}</td>
                    <td className="px-6 py-4">{comp.requirementValue || '-'}</td>
                    <td className="px-6 py-4">{comp.quotationValue || '-'}</td>
                    <td className="px-6 py-4 font-bold text-black">{comp.finalValue || '-'}</td>
                    <td className="px-6 py-4">
                      {getStatusBadge(comp.status)}
                    </td>
                    {hasConfidence && (
                      <td className="px-6 py-4">
                        {comp.confidenceScore !== null ? `${(comp.confidenceScore * 100).toFixed(1)}%` : '-'}
                      </td>
                    )}
                    {hasEvidence && (
                      <td className="px-6 py-4">
                        {comp.evidencePage !== null ? `Pág. ${comp.evidencePage}` : '-'}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
