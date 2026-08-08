import React, { useState, useEffect } from 'react';
import { Code, Download } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { casesService } from '../../../api/cases.service';
import { AppError } from '../../../api/apiError';

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

  useEffect(() => {
    let mounted = true;
    if (caseStatus === 'READY_GENERATE' || caseStatus === 'COMPLETED') {
      casesService.getOutput(caseId)
        .then(res => {
          if (mounted && res) {
            setOutput(res);
          }
        })
        .catch(() => {});
    }
    return () => {
      mounted = false;
    };
  }, [caseId, caseStatus]);

  const handleCompare = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      await casesService.runComparison(caseId);
      onGenerateSuccess();
    } catch (err: any) {
      if (err instanceof AppError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Error inesperado al comparar');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      await casesService.generateHtml(caseId);
      const outRes = await casesService.getOutput(caseId);
      setOutput(outRes);
      onGenerateSuccess();
    } catch (err: any) {
      if (err instanceof AppError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Error inesperado al generar salida');
      }
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

  const handleDownloadHtml = () => {
    if (output) {
      const blob = new Blob([output.html], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `anexo-comparativo-caso-${caseId}.html`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 2000);
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
          <div className="mt-4 flex flex-col gap-2">
            <h4 className="font-semibold mb-1">Versión {output.version} Generada</h4>
            <div className="flex gap-2">
              <Button leftIcon={<Download size={18} />} onClick={handleDownloadHtml}>
                Descargar Anexo HTML
              </Button>
              <Button variant="outline" leftIcon={<Download size={18} />} onClick={handleCopyHtml}>
                Copiar HTML
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
