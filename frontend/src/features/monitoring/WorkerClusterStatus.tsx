import React from 'react';
import { Server, Activity, AlertTriangle, XCircle, CheckCircle2, Clock } from 'lucide-react';
import type { WorkerListResponse, WorkerStatusItem } from '../../types/monitoring';

interface WorkerClusterStatusProps {
  data: WorkerListResponse | null;
  isLoading: boolean;
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function getStatusBadge(status: WorkerStatusItem['status']) {
  switch (status) {
    case 'BUSY':
      return (
        <span className="badge badge-busy">
          <Activity size={14} className="badge-icon spin" />
          PROCESANDO
        </span>
      );
    case 'IDLE':
      return (
        <span className="badge badge-idle">
          <CheckCircle2 size={14} className="badge-icon" />
          DISPONIBLE
        </span>
      );
    case 'UNRESPONSIVE':
      return (
        <span className="badge badge-unresponsive">
          <AlertTriangle size={14} className="badge-icon" />
          NO RESPONSIVO
        </span>
      );
    case 'OFFLINE':
      return (
        <span className="badge badge-offline">
          <XCircle size={14} className="badge-icon" />
          DESCONECTADO
        </span>
      );
    default:
      return <span className="badge">{status}</span>;
  }
}

export const WorkerClusterStatus: React.FC<WorkerClusterStatusProps> = ({ data, isLoading }) => {
  if (isLoading && !data) {
    return (
      <div className="sre-card">
        <div className="sre-card-header">
          <div className="sre-card-title">
            <Server size={20} className="title-icon" />
            <h3>Salud del Cluster de Workers</h3>
          </div>
        </div>
        <div className="sre-loading-placeholder">
          <div className="skeleton skeleton-text" style={{ width: '40%' }}></div>
          <div className="skeleton skeleton-grid"></div>
        </div>
      </div>
    );
  }

  const workers = data?.workers || [];
  const total = data?.total_workers || 0;
  const active = data?.active_workers || 0;
  const unresponsive = data?.unresponsive_workers || 0;
  const offline = data?.offline_workers || 0;

  return (
    <div className="sre-card">
      <div className="sre-card-header">
        <div className="sre-card-title">
          <Server size={20} className="title-icon text-primary" />
          <h3>Salud del Cluster de Workers</h3>
        </div>
        <div className="cluster-summary-badges">
          <span className="summary-pill total">Total: {total}</span>
          <span className="summary-pill active">Activos: {active}</span>
          {unresponsive > 0 && <span className="summary-pill warning">Degradados: {unresponsive}</span>}
          {offline > 0 && <span className="summary-pill danger">Offline: {offline}</span>}
        </div>
      </div>

      <div className="sre-card-body">
        {workers.length === 0 ? (
          <div className="sre-empty-state">
            <AlertTriangle size={32} className="text-muted" />
            <p>No se registran heartbeats de workers en el sistema.</p>
          </div>
        ) : (
          <div className="workers-grid">
            {workers.map((worker) => (
              <div 
                key={worker.worker_name} 
                className={`worker-card status-${worker.status.toLowerCase()}`}
              >
                <div className="worker-card-top">
                  <div className="worker-info">
                    <span className="worker-name">{worker.worker_name}</span>
                    <span className="worker-type">{worker.worker_type}</span>
                  </div>
                  {getStatusBadge(worker.status)}
                </div>

                <div className="worker-card-details">
                  <div className="detail-item">
                    <span className="detail-label">Host:</span>
                    <span className="detail-value">{worker.hostname}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Uptime:</span>
                    <span className="detail-value">{formatUptime(worker.uptime_seconds)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Último latido:</span>
                    <span className="detail-value">
                      <Clock size={12} style={{ display: 'inline', marginRight: 4 }} />
                      hace {Math.round(worker.seconds_since_last_seen)}s
                    </span>
                  </div>
                  {worker.current_job_id && (
                    <div className="detail-item full-width current-job">
                      <span className="detail-label">Job Activo:</span>
                      <code className="job-id-code">{worker.current_job_id}</code>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkerClusterStatus;
