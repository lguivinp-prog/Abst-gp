import React, { useState, useEffect } from 'react';
import { offerService } from '../../../api/v6/offer.service';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { RefreshCw } from 'lucide-react';

interface CaseOfferTermsProps {
  caseId: string;
  offerId: number;
}

export const CaseOfferTerms: React.FC<CaseOfferTermsProps> = ({ caseId, offerId }) => {
  const [terms, setTerms] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchTerms = async () => {
    try {
      setLoading(true);
      const data = await offerService.getOfferTerms(caseId, offerId);
      setTerms(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTerms();
  }, [caseId, offerId]);

  const handleExtract = async () => {
    // In a real flow, this would pass the text/document name from somewhere else.
    // For now, we mock the text as a placeholder.
    try {
      setLoading(true);
      await offerService.extractOfferTerms(caseId, offerId, "extract from pdf", "document.pdf");
      await fetchTerms();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-sm text-gray-500">Cargando condiciones ofertadas...</div>;
  }

  return (
    <div className="mt-6 border-t pt-4">
      <div className="flex justify-between items-center mb-4">
        <h5 className="text-sm font-semibold text-gray-700">Condiciones Ofertadas (Extraídas)</h5>
        <Button variant="outline" size="sm" onClick={handleExtract}>
          <RefreshCw size={14} className="mr-1" /> Re-extraer
        </Button>
      </div>

      {terms.length === 0 ? (
        <p className="text-sm text-gray-500 italic">No hay condiciones contractuales extraídas para esta oferta.</p>
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="p-2 font-medium">Condición</th>
                <th className="p-2 font-medium">Valor Ofertado</th>
                <th className="p-2 font-medium">Fuente</th>
                <th className="p-2 font-medium">Página</th>
                <th className="p-2 font-medium">Confianza</th>
                <th className="p-2 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {terms.map((t, idx) => (
                <tr key={idx}>
                  <td className="p-2">{t.key || 'Término'}</td>
                  <td className="p-2">{t.value_text || t.numeric_value} {t.unit}</td>
                  <td className="p-2 text-gray-500">{t.source_document || '-'}</td>
                  <td className="p-2 text-gray-500">{t.source_page || '-'}</td>
                  <td className="p-2">{t.confidence ? `${(t.confidence * 100).toFixed(0)}%` : '-'}</td>
                  <td className="p-2">
                    <Badge variant={t.review_status === 'REVIEW_REQUIRED' ? 'warning' : 'success'}>
                      {t.review_status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
