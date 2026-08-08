import { useState, useCallback, useRef, useEffect } from 'react';
import { casesService } from '../../../api/cases.service';
import { AppError } from '../../../api/apiError';
import type { ProcessingJobResponse } from '../../../types';

export type NormalizedJobStatus = 'IDLE' | 'QUEUED' | 'PROCESSING' | 'READY' | 'FAILED';

export interface UseJobPollingOptions {
  intervalMs?: number;
  timeoutMs?: number;
  onSuccess?: (job: ProcessingJobResponse) => void;
  onError?: (errorMessage: string) => void;
}

export interface UseJobPollingResult {
  jobId: string | null;
  status: NormalizedJobStatus;
  progress: number;
  message: string;
  error: string | null;
  jobData: ProcessingJobResponse | null;
  isPolling: boolean;
  startPolling: (targetJobId: string) => void;
  cancelPolling: () => void;
  reset: () => void;
}

const DEFAULT_INTERVAL_MS = 2000;
const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

export const normalizeJobStatus = (rawStatus: string | undefined, progress: number): NormalizedJobStatus => {
  if (!rawStatus) {
    return progress >= 100 ? 'READY' : 'PROCESSING';
  }

  const s = rawStatus.toUpperCase();
  if (s === 'READY' || s === 'FINISHED' || progress >= 100) {
    return 'READY';
  }
  if (s === 'FAILED' || s === 'ERROR') {
    return 'FAILED';
  }
  if (s === 'QUEUED' || s === 'DEFERRED') {
    return 'QUEUED';
  }
  if (s === 'PROCESSING' || s === 'STARTED') {
    return 'PROCESSING';
  }

  return 'PROCESSING';
};

export const useJobPolling = (options: UseJobPollingOptions = {}): UseJobPollingResult => {
  const {
    intervalMs = DEFAULT_INTERVAL_MS,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    onSuccess,
    onError,
  } = options;

  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<NormalizedJobStatus>('IDLE');
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [jobData, setJobData] = useState<ProcessingJobResponse | null>(null);
  const [isPolling, setIsPolling] = useState<boolean>(false);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const startTimeRef = useRef<number>(0);

  // Keep latest callbacks in refs to avoid restarting polling on callback changes
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const stopTimers = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (timeoutTimerRef.current) {
      clearTimeout(timeoutTimerRef.current);
      timeoutTimerRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  const cancelPolling = useCallback(() => {
    stopTimers();
    if (isMountedRef.current) {
      setIsPolling(false);
    }
  }, [stopTimers]);

  const reset = useCallback(() => {
    stopTimers();
    if (isMountedRef.current) {
      setJobId(null);
      setStatus('IDLE');
      setProgress(0);
      setMessage('');
      setError(null);
      setJobData(null);
      setIsPolling(false);
    }
  }, [stopTimers]);

  const pollJob = useCallback(async (currentJobId: string) => {
    if (!isMountedRef.current) return;

    // Check timeout
    if (Date.now() - startTimeRef.current > timeoutMs) {
      stopTimers();
      if (isMountedRef.current) {
        const timeoutMsg = 'El proceso excedió el tiempo máximo de espera.';
        setStatus('FAILED');
        setError(timeoutMsg);
        setIsPolling(false);
        if (onErrorRef.current) {
          onErrorRef.current(timeoutMsg);
        }
      }
      return;
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const data = await casesService.getJobStatus(currentJobId, abortController.signal);
      if (!isMountedRef.current) return;

      const currentProgress = typeof data.progress === 'number' ? data.progress : 0;
      const currentMessage = data.message || '';
      const normalizedStatus = normalizeJobStatus(data.status, currentProgress);

      setJobData(data);
      setProgress(currentProgress);
      setMessage(currentMessage);
      setStatus(normalizedStatus);

      if (normalizedStatus === 'READY') {
        stopTimers();
        setIsPolling(false);
        if (onSuccessRef.current) {
          onSuccessRef.current(data);
        }
      } else if (normalizedStatus === 'FAILED') {
        stopTimers();
        const failureMsg = data.error_message || data.message || 'El procesamiento falló en el worker.';
        setError(failureMsg);
        setIsPolling(false);
        if (onErrorRef.current) {
          onErrorRef.current(failureMsg);
        }
      }
    } catch (err: any) {
      if (!isMountedRef.current || abortController.signal.aborted) return;

      if (err instanceof AppError && err.status === 404) {
        stopTimers();
        const notFoundMsg = 'El trabajo no existe o fue eliminado.';
        setStatus('FAILED');
        setError(notFoundMsg);
        setIsPolling(false);
        if (onErrorRef.current) {
          onErrorRef.current(notFoundMsg);
        }
      } else if (err instanceof AppError && err.isNetworkError) {
        // Transient network error: do not stop polling, log warning and let next interval try
        console.warn('Error de red al consultar estado del job, reintentando...', err);
      } else {
        stopTimers();
        const errorMsg = err instanceof AppError ? err.message : 'Error al consultar estado del proceso.';
        setStatus('FAILED');
        setError(errorMsg);
        setIsPolling(false);
        if (onErrorRef.current) {
          onErrorRef.current(errorMsg);
        }
      }
    }
  }, [timeoutMs, stopTimers]);

  const startPolling = useCallback((targetJobId: string) => {
    if (!targetJobId) return;

    stopTimers();

    setJobId(targetJobId);
    setStatus('QUEUED');
    setProgress(0);
    setMessage('Iniciando procesamiento...');
    setError(null);
    setIsPolling(true);
    startTimeRef.current = Date.now();

    // Initial immediate poll
    pollJob(targetJobId);

    // Setup periodic polling interval
    timerRef.current = setInterval(() => {
      pollJob(targetJobId);
    }, intervalMs);
  }, [intervalMs, stopTimers, pollJob]);

  // Clean up on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      stopTimers();
    };
  }, [stopTimers]);

  return {
    jobId,
    status,
    progress,
    message,
    error,
    jobData,
    isPolling,
    startPolling,
    cancelPolling,
    reset,
  };
};
