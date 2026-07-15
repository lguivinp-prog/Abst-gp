import React, { useEffect, useState } from 'react';
import apiClient from '../../../api/client';
import { Card, CardContent } from '../../../components/ui/Card';

interface ProcessingStatusProps {
  jobId: string;
  onComplete: () => void;
}

export const ProcessingStatus: React.FC<ProcessingStatusProps> = ({ jobId, onComplete }) => {
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('Iniciando...');
  const [status, setStatus] = useState('queued');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      setErrorMsg('No se recibió ID de procesamiento.');
      setStatus('failed');
      return;
    }

    const interval = setInterval(async () => {
      try {
        const res = await apiClient.get(`/cases/jobs/${jobId}`);
        setProgress(res.data.progress || 0);
        setMessage(res.data.message || '');
        setStatus(res.data.status);
        
        if (res.data.status === 'finished' || res.data.progress === 100) {
          clearInterval(interval);
          onComplete();
        } else if (res.data.status === 'failed') {
          clearInterval(interval);
          onComplete();
        }
      } catch (err: any) {
        console.error("Error polling job", err);
        clearInterval(interval);
        setStatus('failed');
        let errorText = 'Error consultando estado del proceso';
        if (err.response?.data?.detail) {
          if (typeof err.response.data.detail === 'string') {
            errorText = err.response.data.detail;
          } else if (Array.isArray(err.response.data.detail)) {
            errorText = err.response.data.detail.map((e: any) => e.msg).join(', ');
          } else {
            errorText = JSON.stringify(err.response.data.detail);
          }
        }
        setErrorMsg(errorText);
        onComplete();
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [jobId, onComplete]);

  return (
    <Card className="mb-4">
      <CardContent className="pt-4">
        <h3 className="font-medium text-lg mb-2">Procesando OCR</h3>
        {errorMsg && <div className="text-red-600 mb-4 text-sm bg-red-50 p-2 rounded">{errorMsg}</div>}
        <p className="text-sm text-gray-600 mb-4">{message}</p>
        <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
          <div className={`h-2.5 rounded-full ${status === 'failed' ? 'bg-red-600' : 'bg-blue-600'}`} style={{ width: `${progress}%` }}></div>
        </div>
        <p className="text-right text-xs text-gray-500">{progress}%</p>
      </CardContent>
    </Card>
  );
};
