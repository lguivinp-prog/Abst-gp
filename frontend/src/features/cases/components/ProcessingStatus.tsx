import React, { useEffect } from 'react';
import { Card, CardContent } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { useJobPolling } from '../hooks/useJobPolling';

interface ProcessingStatusProps {
  jobId: string;
  title?: string;
  onComplete: () => void;
  onRetry?: () => void;
}

export const ProcessingStatus: React.FC<ProcessingStatusProps> = ({ 
  jobId, 
  title = 'Procesando OCR', 
  onComplete, 
  onRetry 
}) => {
  const { status, progress, message, error, startPolling } = useJobPolling({
    onSuccess: () => {
      onComplete();
    },
  });

  useEffect(() => {
    if (jobId) {
      startPolling(jobId);
    }
  }, [jobId, startPolling]);

  return (
    <Card className="mb-4 border border-blue-100 shadow-sm">
      <CardContent className="pt-4">
        <div className="flex justify-between items-center mb-2">
          <h3 className="font-medium text-lg text-gray-800">{title}</h3>
          {status === 'FAILED' && <Badge variant="danger">Error</Badge>}
        </div>
        
        {error && (
          <div className="flex flex-col gap-3 bg-red-50 p-3 rounded-md border border-red-100 mb-4">
            <div className="flex items-start gap-2 text-red-700">
              <AlertCircle size={18} className="mt-0.5" />
              <span className="text-sm font-medium">{error}</span>
            </div>
            {onRetry && (
              <div className="flex justify-end">
                <Button variant="outline" size="sm" onClick={onRetry} leftIcon={<RefreshCw size={14} />}>
                  Reintentar
                </Button>
              </div>
            )}
          </div>
        )}
        
        <p className="text-sm text-gray-600 mb-3">{message || (status === 'QUEUED' ? 'En cola de procesamiento...' : 'Procesando...')}</p>
        
        <div className="w-full bg-gray-200 rounded-full h-2 mb-1 overflow-hidden">
          <div 
            className={`h-2 rounded-full transition-all duration-300 ease-out ${status === 'FAILED' ? 'bg-red-500' : 'bg-blue-600'}`} 
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-right text-xs text-gray-500 font-medium">{progress}%</p>
      </CardContent>
    </Card>
  );
};

const Badge = ({ children, variant }: { children: React.ReactNode, variant: string }) => (
  <span className={`px-2 py-1 text-xs font-semibold rounded-full ${variant === 'danger' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'}`}>
    {children}
  </span>
);
