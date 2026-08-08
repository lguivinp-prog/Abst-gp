import React, { useState } from 'react';
import { RefreshCw, ShieldAlert, CheckCircle2, RotateCcw, AlertTriangle, PlayCircle } from 'lucide-react';
import type { RecoverySummaryResponse, RecoveryTriggerResponse } from '../../types/monitoring';

interface RecoveryControlPanelProps {
  data: RecoverySummaryResponse | null;
  isLoading: boolean;
  onTriggerRecovery: () => Promise<RecoveryTriggerResponse | null>;
  isTriggering: boolean;
  lastResult: RecoveryTriggerResponse | null;
}

export const RecoveryControlPanel: React.FC<RecoveryControlPanelProps> = ({
  data,
  isLoading,
  onTriggerRecovery,
  isTriggering,
  lastResult,
}) => {
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);

  const staleProcessing = data?.stale_processing_count || 0;
  const staleQueued = data?.stale_queued_count || 0;
  const totalStale = staleProcessing + staleQueued;

  const handleConfirmTrigger = async () => {
    setShowConfirmModal(false);
    await onTriggerRecovery();
  };

  return (
    <div className="sre-card">
      <div className="sre-card-header">
        <div className="sre-card-title">
          <RotateCcw size={20} className="title-icon text-warning" />
          <h3>Panel de Resiliencia & Recuperación Automática</h3>
        </div>

        <div className="recovery-action-area">
          <button
            type="button"
            className="btn-trigger-recovery"
            onClick={() => setShowConfirmModal(true)}
            disabled={isTriggering || isLoading}
          >
            {isTriggering ? (
              <>
                <RefreshCw size={16} className="spin" />
                Reconciliando...
              </>
            ) : (
              <>
                <PlayCircle size={16} />
                Ejecutar Reconciliación Manual
              </>
            )}
          </button>
        </div>
      </div>

      <div className="sre-card-body">
        {/* KPI Mini Grid */}
        <div className="recovery-kpi-grid">
          <div className={`recovery-kpi-card ${staleProcessing > 0 ? 'border-warning' : ''}`}>
            <span className="recovery-kpi-label">Processing Estancados</span>
            <span className={`recovery-kpi-value ${staleProcessing > 0 ? 'text-warning' : 'text-success'}`}>
              {staleProcessing}
            </span>
            <span className="recovery-kpi-sub">&gt; 30s sin heartbeat</span>
          </div>

          <div className={`recovery-kpi-card ${staleQueued > 0 ? 'border-warning' : ''}`}>
            <span className="recovery-kpi-label">Queued Estancados</span>
            <span className={`recovery-kpi-value ${staleQueued > 0 ? 'text-warning' : 'text-success'}`}>
              {staleQueued}
            </span>
            <span className="recovery-kpi-sub">&gt; 300s en cola</span>
          </div>

          <div className="recovery-kpi-card">
            <span className="recovery-kpi-label">Recuperados Histórico</span>
            <span className="recovery-kpi-value text-primary">
              {data?.recovered_jobs_count || 0}
            </span>
            <span className="recovery-kpi-sub">Reintentados exitosamente</span>
          </div>

          <div className="recovery-kpi-card">
            <span className="recovery-kpi-label">Fallidos Terminales</span>
            <span className="recovery-kpi-value text-muted">
              {data?.failed_final_count || 0}
            </span>
            <span className="recovery-kpi-sub">Max retries o datos corruptos</span>
          </div>
        </div>

        {/* Feedback del último resultado */}
        {lastResult && (
          <div className="recovery-result-banner">
            <CheckCircle2 size={20} className="text-success" />
            <div className="result-text">
              <strong>Reconciliación Ejecutada:</strong> {lastResult.message}.{' '}
              <span>
                Escaneados: {lastResult.total_scanned} | Reintentados: {lastResult.recovered_retried} | Marcados Final: {lastResult.marked_failed_final + lastResult.marked_failed_max_retries}
              </span>
            </div>
          </div>
        )}

        {/* Lista de Jobs Estancados */}
        {totalStale > 0 ? (
          <div className="stale-jobs-section">
            <div className="stale-jobs-header">
              <ShieldAlert size={16} className="text-warning" />
              <h4>Trabajos Requiriendo Intervención ({totalStale})</h4>
            </div>

            <div className="stale-jobs-table-wrapper">
              <table className="sre-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Tipo</th>
                    <th>Estado</th>
                    <th>Intentos / Max</th>
                    <th>Tiempo Estancado</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.stale_processing_jobs.map((job) => (
                    <tr key={job.job_id}>
                      <td><code className="job-id-code">{job.job_id}</code></td>
                      <td><span className="job-type-pill">{job.job_type}</span></td>
                      <td><span className="badge badge-unresponsive">{job.status}</span></td>
                      <td>{job.attempt_count} / {job.max_retries}</td>
                      <td>{Math.round(job.stale_duration_sec)}s</td>
                    </tr>
                  ))}
                  {data?.stale_queued_jobs.map((job) => (
                    <tr key={job.job_id}>
                      <td><code className="job-id-code">{job.job_id}</code></td>
                      <td><span className="job-type-pill">{job.job_type}</span></td>
                      <td><span className="badge badge-busy">{job.status}</span></td>
                      <td>{job.attempt_count} / {job.max_retries}</td>
                      <td>{Math.round(job.stale_duration_sec)}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="sre-empty-state success" style={{ marginTop: '16px' }}>
            <CheckCircle2 size={28} className="text-success" />
            <p>No existen trabajos huérfanos ni estancados pendientes de recuperación.</p>
          </div>
        )}
      </div>

      {/* Modal de Confirmación de Reconciliación */}
      {showConfirmModal && (
        <div className="sre-modal-overlay">
          <div className="sre-modal">
            <div className="sre-modal-header">
              <AlertTriangle size={24} className="text-warning" />
              <h3>Confirmar Reconciliación de Jobs</h3>
            </div>
            <div className="sre-modal-body">
              <p>
                Esta acción ejecutará el <strong>JobRecoveryEngine</strong> en la base de datos PostgreSQL con bloqueo pesimista <code>SELECT FOR UPDATE</code>.
              </p>
              <p>
                Los jobs con fallos recuperables serán reencolados con backoff exponencial. Se registrará un evento inmutable en <code>AuditLog</code>.
              </p>
            </div>
            <div className="sre-modal-footer">
              <button
                type="button"
                className="btn-modal-cancel"
                onClick={() => setShowConfirmModal(false)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="btn-modal-confirm"
                onClick={handleConfirmTrigger}
              >
                Confirmar y Ejecutar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RecoveryControlPanel;
