import { useState, useEffect, useCallback } from 'react';
import { casesService } from '../../../api/cases.service';
import { AppError } from '../../../api/apiError';

interface UseRequirementDocumentResult {
  blobUrl: string | null;
  isLoading: boolean;
  error: AppError | null;
  isNotAvailable: boolean; // 404 specific state
  retry: () => void;
}

export const useRequirementDocument = (caseId: string | undefined): UseRequirementDocumentResult => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<AppError | null>(null);
  const [isNotAvailable, setIsNotAvailable] = useState<boolean>(false);
  const [retryCount, setRetryCount] = useState<number>(0);

  const retry = useCallback(() => {
    setRetryCount(prev => prev + 1);
  }, []);

  useEffect(() => {
    if (!caseId) {
      setBlobUrl(null);
      setError(null);
      setIsNotAvailable(false);
      return;
    }

    const abortController = new AbortController();
    let currentObjectUrl: string | null = null;

    const fetchDocument = async () => {
      setIsLoading(true);
      setError(null);
      setIsNotAvailable(false);

      try {
        const blob = await casesService.getRequirementDocumentBlob(caseId, abortController.signal);
        
        if (abortController.signal.aborted) {
          return; // Ignore result if aborted
        }

        currentObjectUrl = URL.createObjectURL(blob);
        setBlobUrl(currentObjectUrl);
      } catch (err: any) {
        if (abortController.signal.aborted) {
          return; // Ignore if aborted
        }

        const appError = err as AppError;
        
        if (appError.status === 404) {
          setIsNotAvailable(true);
        } else {
          setError(appError);
        }
        
        // Revoke any existing URL just in case
        setBlobUrl(null);
      } finally {
        if (!abortController.signal.aborted) {
          setIsLoading(false);
        }
      }
    };

    fetchDocument();

    return () => {
      // 1. Cancel ongoing request
      abortController.abort();
      
      // 2. Revoke the object URL to prevent memory leaks
      if (currentObjectUrl) {
        URL.revokeObjectURL(currentObjectUrl);
      }
    };
  }, [caseId, retryCount]); // Re-run if caseId changes or retry is triggered

  return { blobUrl, isLoading, error, isNotAvailable, retry };
};
