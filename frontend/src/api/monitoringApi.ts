import apiClient from './client';
import type {
  WorkerListResponse,
  LatencyReportResponse,
  ErrorAnalyticsResponse,
  RecoverySummaryResponse,
  RecoveryTriggerResponse,
} from '../types/monitoring';

export interface WorkerStatusParams {
  heartbeat_threshold_sec?: number;
  tenant_id?: string;
}

export interface LatencyParams {
  job_type?: string;
  hours?: number;
  tenant_id?: string;
}

export interface ErrorParams {
  hours?: number;
  tenant_id?: string;
}

export interface RecoveryStatusParams {
  heartbeat_timeout_sec?: number;
  queued_timeout_sec?: number;
  tenant_id?: string;
}

export interface RecoveryTriggerParams {
  tenant_id?: string;
}

export const monitoringApi = {
  /**
   * Obtiene la salud y estado de liveness del cluster de workers en tiempo real.
   */
  async getWorkersStatus(params?: WorkerStatusParams, signal?: AbortSignal): Promise<WorkerListResponse> {
    const response = await apiClient.get<WorkerListResponse>('/admin/monitoring/workers', {
      params,
      signal,
    });
    return response.data;
  },

  /**
   * Obtiene el reporte de latencias y percentiles de SLA (p50, p95, p99).
   */
  async getLatencyMetrics(params?: LatencyParams, signal?: AbortSignal): Promise<LatencyReportResponse> {
    const response = await apiClient.get<LatencyReportResponse>('/admin/monitoring/latencies', {
      params,
      signal,
    });
    return response.data;
  },

  /**
   * Obtiene la matriz de errores agrupada por categoría, código y job_type.
   */
  async getErrorAnalytics(params?: ErrorParams, signal?: AbortSignal): Promise<ErrorAnalyticsResponse> {
    const response = await apiClient.get<ErrorAnalyticsResponse>('/admin/monitoring/errors', {
      params,
      signal,
    });
    return response.data;
  },

  /**
   * Obtiene el resumen de jobs estancados y estado de resiliencia (Read-Only).
   */
  async getRecoveryStatus(params?: RecoveryStatusParams, signal?: AbortSignal): Promise<RecoverySummaryResponse> {
    const response = await apiClient.get<RecoverySummaryResponse>('/admin/monitoring/recovery', {
      params,
      signal,
    });
    return response.data;
  },

  /**
   * Dispara una reconciliación manual de jobs con bloqueo pesimista y auditoría.
   */
  async triggerRecoveryReconciliation(params?: RecoveryTriggerParams): Promise<RecoveryTriggerResponse> {
    const response = await apiClient.post<RecoveryTriggerResponse>('/admin/monitoring/recovery/trigger', null, {
      params,
    });
    return response.data;
  },
};

export default monitoringApi;
