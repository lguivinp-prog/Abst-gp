import { useState, useEffect, useCallback, useRef } from 'react';
import monitoringApi from '../api/monitoringApi';
import type {
  WorkerListResponse,
  LatencyReportResponse,
  ErrorAnalyticsResponse,
  RecoverySummaryResponse,
  RecoveryTriggerResponse,
} from '../types/monitoring';

export interface UseSREMonitoringOptions {
  pollingIntervalMs?: number;
  initialTimeWindowHours?: number;
  initialJobType?: string;
  autoRefreshEnabled?: boolean;
}

export interface UseSREMonitoringReturn {
  workersData: WorkerListResponse | null;
  latencyData: LatencyReportResponse | null;
  errorData: ErrorAnalyticsResponse | null;
  recoveryData: RecoverySummaryResponse | null;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  lastUpdated: Date | null;
  isAutoRefreshActive: boolean;
  timeWindowHours: number;
  setTimeWindowHours: (hours: number) => void;
  jobTypeFilter: string;
  setJobTypeFilter: (jobType: string) => void;
  toggleAutoRefresh: () => void;
  refetch: () => Promise<void>;
  triggerRecovery: () => Promise<RecoveryTriggerResponse | null>;
  isTriggeringRecovery: boolean;
  lastRecoveryResult: RecoveryTriggerResponse | null;
}

export function useSREMonitoring(options: UseSREMonitoringOptions = {}): UseSREMonitoringReturn {
  const {
    pollingIntervalMs = 10000,
    initialTimeWindowHours = 24,
    initialJobType = 'ALL',
    autoRefreshEnabled = true,
  } = options;

  const [workersData, setWorkersData] = useState<WorkerListResponse | null>(null);
  const [latencyData, setLatencyData] = useState<LatencyReportResponse | null>(null);
  const [errorData, setErrorData] = useState<ErrorAnalyticsResponse | null>(null);
  const [recoveryData, setRecoveryData] = useState<RecoverySummaryResponse | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [isAutoRefreshActive, setIsAutoRefreshActive] = useState<boolean>(autoRefreshEnabled);
  const [timeWindowHours, setTimeWindowHours] = useState<number>(initialTimeWindowHours);
  const [jobTypeFilter, setJobTypeFilter] = useState<string>(initialJobType);

  const [isTriggeringRecovery, setIsTriggeringRecovery] = useState<boolean>(false);
  const [lastRecoveryResult, setLastRecoveryResult] = useState<RecoveryTriggerResponse | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const isInitialLoadRef = useRef<boolean>(true);

  const fetchMetrics = useCallback(async () => {
    // Cancel previous inflight request if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    if (isInitialLoadRef.current) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    setError(null);

    try {
      const latencyParams: { job_type?: string; hours: number } = {
        hours: timeWindowHours,
      };
      if (jobTypeFilter && jobTypeFilter !== 'ALL') {
        latencyParams.job_type = jobTypeFilter;
      }

      const [workersRes, latencyRes, errorRes, recoveryRes] = await Promise.all([
        monitoringApi.getWorkersStatus({}, controller.signal),
        monitoringApi.getLatencyMetrics(latencyParams, controller.signal),
        monitoringApi.getErrorAnalytics({ hours: timeWindowHours }, controller.signal),
        monitoringApi.getRecoveryStatus({}, controller.signal),
      ]);

      setWorkersData(workersRes);
      setLatencyData(latencyRes);
      setErrorData(errorRes);
      setRecoveryData(recoveryRes);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'CanceledError') {
        // Ignorar cancelaciones intencionales
        return;
      }
      const message = err instanceof Error ? err.message : 'Error al consultar telemetría SRE';
      setError(message);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
      isInitialLoadRef.current = false;
    }
  }, [timeWindowHours, jobTypeFilter]);

  // Trigger reconciliación manual
  const triggerRecovery = useCallback(async (): Promise<RecoveryTriggerResponse | null> => {
    setIsTriggeringRecovery(true);
    try {
      const result = await monitoringApi.triggerRecoveryReconciliation();
      setLastRecoveryResult(result);
      // Refrescar métricas inmediatamente después de la reconciliación
      await fetchMetrics();
      return result;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Error al ejecutar reconciliación SRE';
      setError(message);
      return null;
    } finally {
      setIsTriggeringRecovery(false);
    }
  }, [fetchMetrics]);

  const toggleAutoRefresh = useCallback(() => {
    setIsAutoRefreshActive((prev) => !prev);
  }, []);

  // Efecto para fetch inicial y cuando cambian los filtros
  useEffect(() => {
    fetchMetrics();

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchMetrics]);

  // Efecto para polling continuo
  useEffect(() => {
    if (!isAutoRefreshActive) return;

    const intervalId = setInterval(() => {
      fetchMetrics();
    }, pollingIntervalMs);

    return () => {
      clearInterval(intervalId);
    };
  }, [isAutoRefreshActive, pollingIntervalMs, fetchMetrics]);

  return {
    workersData,
    latencyData,
    errorData,
    recoveryData,
    isLoading,
    isRefreshing,
    error,
    lastUpdated,
    isAutoRefreshActive,
    timeWindowHours,
    setTimeWindowHours,
    jobTypeFilter,
    setJobTypeFilter,
    toggleAutoRefresh,
    refetch: fetchMetrics,
    triggerRecovery,
    isTriggeringRecovery,
    lastRecoveryResult,
  };
}

export default useSREMonitoring;
