import React, { useState } from 'react';
import { Upload, AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { Card, CardHeader, CardTitle, CardContent } from '../../../components/ui/Card';
import { casesService } from '../../../api/cases.service';
import { AppError } from '../../../api/apiError';
import { MAX_QUOTATION_SIZE_MB } from '../../../config/documentLimits';
import { useJobPolling } from '../hooks/useJobPolling';

interface QuotationUploadProps {
  caseId: string;
  onUploadSuccess: () => void;
  disabled: boolean;
}

export const QuotationUpload: React.FC<QuotationUploadProps> = ({ caseId, onUploadSuccess, disabled }) => {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const {
    status: pollingStatus,
    progress,
    message,
    error: pollingError,
    isPolling,
    startPolling,
    reset: resetPolling,
  } = useJobPolling({
    onSuccess: () => {
      onUploadSuccess();
    },
  });

  const handleUpload = async () => {
    if (!file) return;

    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > MAX_QUOTATION_SIZE_MB) {
      setUploadError(`El archivo excede el tamaño máximo permitido de ${MAX_QUOTATION_SIZE_MB}MB.`);
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    resetPolling();

    try {
      const response = await casesService.uploadQuotation(caseId, file);
      
      // If async mode with job_id returned
      if (response && response.job_id) {
        startPolling(response.job_id);
      } else {
        // Synchronous mode fallback (V5.2.1)
        onUploadSuccess();
      }
    } catch (error: any) {
      if (error instanceof AppError) {
        if (error.isNetworkError) {
          setUploadError('Se perdió la conexión durante la subida, pero el servidor podría seguir procesando. Verifique el estado en unos minutos.');
        } else {
          setUploadError(error.message);
        }
      } else {
        setUploadError('Error inesperado al subir cotización.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  const handleRetry = () => {
    resetPolling();
    setUploadError(null);
    setFile(null);
  };

  const isProcessing = isUploading || isPolling || (pollingStatus !== 'IDLE' && pollingStatus !== 'READY' && pollingStatus !== 'FAILED');
  const activeError = uploadError || pollingError;

  return (
    <Card className={disabled ? 'opacity-50' : ''}>
      <CardHeader>
        <CardTitle>2. Cotización</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm mb-4">Suba la cotización del proveedor para extraer condiciones.</p>
        
        {activeError && (
          <div className="flex flex-col gap-3 bg-red-50 p-3 rounded-md border border-red-100 mb-4">
            <div className="flex items-start gap-2 text-red-700">
              <AlertCircle size={18} className="mt-0.5 shrink-0" />
              <span className="text-sm font-medium">{activeError}</span>
            </div>
            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={handleRetry} leftIcon={<RefreshCw size={14} />}>
                Reintentar
              </Button>
            </div>
          </div>
        )}
        
        {isProcessing ? (
          <div className="bg-blue-50 border border-blue-100 p-4 rounded-md flex flex-col mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-blue-800">
                {isUploading ? 'Subiendo archivo...' : 'Extrayendo condiciones de la cotización...'}
              </span>
              <span className="text-xs font-semibold text-blue-700">{progress}%</span>
            </div>
            
            <div className="w-full bg-blue-200 rounded-full h-2 mb-2 overflow-hidden">
              <div 
                className="bg-blue-600 h-2 rounded-full transition-all duration-300 ease-out" 
                style={{ width: `${isUploading ? 10 : Math.max(progress, 15)}%` }}
              />
            </div>
            
            <p className="text-xs text-blue-600">
              {message || 'La duración depende del tamaño y complejidad del documento. No recargue la página.'}
            </p>
          </div>
        ) : (
          <>
            <input 
              type="file" 
              data-testid="upload-quotation"
              accept="application/pdf" 
              onChange={(e) => {
                setFile(e.target.files?.[0] || null);
                setUploadError(null);
              }} 
              className="mb-4 block w-full text-sm text-gray-500
                file:mr-4 file:py-2 file:px-4
                file:rounded-md file:border-0
                file:text-sm file:font-semibold
                file:bg-blue-50 file:text-blue-700
                hover:file:bg-blue-100" 
              disabled={disabled || isProcessing}
            />
            
            <Button 
              leftIcon={<Upload size={18} />} 
              onClick={handleUpload} 
              disabled={!file || disabled || isProcessing}
            >
              Subir Cotización
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
};
