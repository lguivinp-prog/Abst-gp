import { useState, useCallback, useRef, useEffect } from 'react';
import { casesService } from '../../../api/cases.service';
import type { ConditionComparison } from '../domain/models';
import { AppError } from '../../../api/apiError';
import { normalizeJobStatus } from './useJobPolling';

interface UseComparisonFlowResult {
  comparisons: ConditionComparison[];
  isLoading: boolean;
  isExecuting: boolean;
  error: AppError | null;
  status: 'idle' | 'running' | 'completed' | 'uncertain';
  executeComparison: () => Promise<void>;
  refreshResults: () => Promise<void>;
}

const COMPARISON_POLL_INTERVAL_MS = 2000;
const COMPARISON_POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

export const useComparisonFlow = (
  caseId: string, 
  initialCaseStatus: string,
  onStatusChange?: (newStatus: string) => void
): UseComparisonFlowResult => {
  const [comparisons, setComparisons] = useState<ConditionComparison[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [error, setError] = useState<AppError | null>(null);
  
  // Derived or explicit status
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'uncertain'>(
    initialCaseStatus === 'READY_GENERATE' ? 'completed' : 'idle'
  );

  const runInFlightRef = useRef<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const refreshResults = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError(null);
    try {
      const results = await casesService.getComparison(caseId, signal);
      setComparisons(results);
      if (results.length > 0) {
        setStatus('completed');
      }
    } catch (err) {
      if (signal?.aborted) return;
      setError(err as AppError);
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, [caseId]);

  // Initial load if already READY_GENERATE
  useEffect(() => {
    if (initialCaseStatus === 'READY_GENERATE') {
      const abortController = new AbortController();
      refreshResults(abortController.signal);
      return () => abortController.abort();
    }
  }, [caseId, initialCaseStatus, refreshResults]);

  const pollComparisonJob = useCallback(async (jobId: string, signal: AbortSignal): Promise<void> => {
    const startTime = Date.now();

    while (!signal.aborted) {
      if (Date.now() - startTime > COMPARISON_POLL_TIMEOUT_MS) {
        throw new AppError(504, 'El proceso de comparación excedió el tiempo máximo de espera.');
      }

      try {
        const jobData = await casesService.getJobStatus(jobId, signal);
        if (signal.aborted) return;

        const normStatus = normalizeJobStatus(jobData.status, jobData.progress);

        if (normStatus === 'READY') {
          return;
        }

        if (normStatus === 'FAILED') {
          throw new AppError(500, jobData.error_message || jobData.message || 'Error durante el procesamiento de la comparación.');
        }
      } catch (err: any) {
        if (signal.aborted) return;
        if (err instanceof AppError && err.status === 404) {
          throw new AppError(404, 'El trabajo de comparación no existe o fue eliminado.');
        }
        if (err instanceof AppError && !err.isNetworkError) {
          throw err;
        }
        // Transient network errors continue to next poll tick
      }

      // Wait interval before next poll check
      await new Promise((resolve) => setTimeout(resolve, COMPARISON_POLL_INTERVAL_MS));
    }
  }, []);

  const executeComparison = useCallback(async () => {
    if (runInFlightRef.current || status === 'completed') return;
    
    runInFlightRef.current = true;
    setIsExecuting(true);
    setError(null);
    setStatus('running');

    // Create a new abort controller for this specific run
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const response = await casesService.runComparison(caseId, abortController.signal);
      
      if (abortController.signal.aborted) return;

      // If async response with job_id, poll until job finishes
      if (response && response.job_id && !response.alreadyCompleted && !response.already_completed) {
        await pollComparisonJob(response.job_id, abortController.signal);
      }
      
      if (abortController.signal.aborted) return;

      // Fetch comparison results
      await refreshResults(abortController.signal);
      
      if (!abortController.signal.aborted) {
        setStatus('completed');
        if (onStatusChange) {
          onStatusChange('READY_GENERATE');
        }
      }
    } catch (err: any) {
      if (abortController.signal.aborted) return;

      const appError = err instanceof AppError ? err : new AppError(500, err?.message || 'Error durante la comparación');
      
      // Handle network errors, 502, 504 timeouts -> uncertain
      if (
        appError.isNetworkError || 
        appError.status === 504 || 
        appError.status === 502 || 
        appError.code === 'ECONNABORTED'
      ) {
        setStatus('uncertain');
      } else {
        setStatus('idle');
      }
      
      setError(appError);
    } finally {
      if (!abortController.signal.aborted) {
        setIsExecuting(false);
        runInFlightRef.current = false;
      }
    }
  }, [caseId, status, refreshResults, onStatusChange, pollComparisonJob]);

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return {
    comparisons,
    isLoading,
    isExecuting,
    error,
    status,
    executeComparison,
    refreshResults
  };
};
