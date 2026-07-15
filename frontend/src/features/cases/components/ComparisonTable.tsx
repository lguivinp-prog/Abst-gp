import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';

interface ComparisonResult {
  field_name: string;
  requirement_value?: string;
  quotation_value?: string;
  final_value?: string;
  status: string;
}

interface ComparisonTableProps {
  comparisons: ComparisonResult[];
}

export const ComparisonTable: React.FC<ComparisonTableProps> = ({ comparisons }) => {
  if (!comparisons || comparisons.length === 0) return null;

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Resultados de la Comparación</CardTitle>
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
              </tr>
            </thead>
            <tbody>
              {comparisons.map((comp, idx) => (
                <tr key={idx} className="bg-white border-b">
                  <td className="px-6 py-4 font-medium text-gray-900">{comp.field_name}</td>
                  <td className="px-6 py-4">{comp.requirement_value}</td>
                  <td className="px-6 py-4">{comp.quotation_value}</td>
                  <td className="px-6 py-4 font-bold text-black">{comp.final_value}</td>
                  <td className="px-6 py-4">
                    <Badge variant={comp.status === 'MATCH' ? 'success' : 'warning'}>
                      {comp.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};
