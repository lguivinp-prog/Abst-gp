import React, { useState } from 'react';
import { Code, Download } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import apiClient from '../../../api/client';

interface OutputGeneratorProps {
  caseId: string;
  caseStatus: string;
  disabled: boolean;
  onGenerateSuccess: () => void;
}

export const OutputGenerator: React.FC<OutputGeneratorProps> = ({ caseId, caseStatus, disabled, onGenerateSuccess }) => {
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState<{html: string, plain_text: string, version: number} | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleCompare = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      await apiClient.post(`/cases/${caseId}/comparison/run`);
      onGenerateSuccess();
    } catch (err: any) {
      console.error('Error in comparison:', err);
      setErrorMsg(err.response?.data?.detail || 'Error al comparar');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      await apiClient.post(`/cases/${caseId}/generate/html`);
      const outRes = await apiClient.get(`/cases/${caseId}/output`);
      setOutput(outRes.data);
      onGenerateSuccess();
    } catch (err: any) {
      console.error('Error generating output:', err);
      setErrorMsg(err.response?.data?.detail || 'Error al generar salida');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyHtml = () => {
    if (output) {
      navigator.clipboard.writeText(output.html);
      alert('HTML Copiado al portapapeles');
    }
  };

  return (
    <Card className={disabled ? 'opacity-50' : ''}>
      <CardHeader>
        <CardTitle>3. Generación Final</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm mb-4">Compare y genere el Anexo final.</p>
        {errorMsg && <div className="text-red-600 mb-4 text-sm bg-red-50 p-2 rounded">{errorMsg}</div>}
        {!output ? (
          caseStatus === 'COMPARING' ? (
            <Button 
              leftIcon={<Code size={18} />} 
              onClick={handleCompare} 
              disabled={disabled || loading}
            >
              {loading ? 'Procesando...' : 'Comparar Requerimiento vs Cotización'}
            </Button>
          ) : (
            <Button 
              leftIcon={<Code size={18} />} 
              onClick={handleGenerate} 
              disabled={disabled || loading}
            >
              {loading ? 'Generando...' : 'Generar Anexo Final'}
            </Button>
          )
        ) : (
          <div className="mt-4">
            <h4 className="font-semibold mb-2">Versión {output.version} Generada</h4>
            <Button leftIcon={<Download size={18} />} onClick={handleCopyHtml}>Copiar HTML</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
