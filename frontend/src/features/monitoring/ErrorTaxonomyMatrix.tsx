import React from 'react';
import { AlertOctagon, ShieldAlert, FileX, Terminal, CheckCircle2 } from 'lucide-react';
import type { ErrorAnalyticsResponse } from '../../types/monitoring';

interface ErrorTaxonomyMatrixProps {
  data: ErrorAnalyticsResponse | null;
  isLoading: boolean;
}

function getCategoryIcon(category: string) {
  switch (category) {
    case 'TRANSIENT_INFRA':
      return <Terminal size={16} className="category-icon text-warning" />;
    case 'CORRUPT_INPUT':
      return <FileX size={16} className="category-icon text-danger" />;
    case 'BUSINESS_RULE':
      return <ShieldAlert size={16} className="category-icon text-info" />;
    default:
      return <AlertOctagon size={16} className="category-icon text-muted" />;
  }
}

function getCategoryBadge(category: string) {
  const isRetryable = category === 'TRANSIENT_INFRA';
  return (
    <span className={`badge ${isRetryable ? 'badge-retryable' : 'badge-final'}`}>
      {isRetryable ? 'REINTENTABLE' : 'FINAL'}
    </span>
  );
}

export const ErrorTaxonomyMatrix: React.FC<ErrorTaxonomyMatrixProps> = ({ data, isLoading }) => {
  if (isLoading && !data) {
    return (
      <div className="sre-card">
        <div className="sre-card-header">
          <div className="sre-card-title">
            <AlertOctagon size={20} className="title-icon" />
            <h3>Taxonomía & Matriz de Errores V5.4</h3>
          </div>
        </div>
        <div className="sre-loading-placeholder">
          <div className="skeleton skeleton-grid" style={{ height: '140px' }}></div>
        </div>
      </div>
    );
  }

  const totalProcessed = data?.total_processed || 0;
  const failedJobs = data?.failed_jobs || 0;
  const failureRate = data?.failure_rate_percent || 0;
  const categories = Object.entries(data?.errors_by_category || {});
  const codes = Object.entries(data?.errors_by_code || {});
  const jobTypes = Object.entries(data?.errors_by_job_type || {});

  return (
    <div className="sre-card">
      <div className="sre-card-header">
        <div className="sre-card-title">
          <AlertOctagon size={20} className="title-icon text-danger" />
          <h3>Taxonomía & Matriz de Errores V5.4</h3>
        </div>
        <div className="error-rate-indicator">
          <span className="rate-label">Tasa de Fallo:</span>
          <span className={`rate-value ${failureRate > 5 ? 'text-danger' : failureRate > 0 ? 'text-warning' : 'text-success'}`}>
            {failureRate.toFixed(2)}%
          </span>
          <span className="rate-count">({failedJobs} / {totalProcessed} jobs)</span>
        </div>
      </div>

      <div className="sre-card-body">
        {failedJobs === 0 ? (
          <div className="sre-empty-state success">
            <CheckCircle2 size={36} className="text-success" />
            <h4>Cero Fallos en la Ventana Seleccionada</h4>
            <p>El pipeline opera con 100% de éxito en los últimos {data?.time_window_hours || 24} horas.</p>
          </div>
        ) : (
          <div className="error-analytics-layout">
            {/* Categorías Principales */}
            <div className="error-categories-section">
              <h4 className="section-title">Distribución por Categoría</h4>
              <div className="categories-list">
                {categories.map(([cat, count]) => {
                  const percent = failedJobs > 0 ? (count / failedJobs) * 100 : 0;
                  return (
                    <div key={cat} className="category-row">
                      <div className="category-name-group">
                        {getCategoryIcon(cat)}
                        <span className="category-name">{cat}</span>
                        {getCategoryBadge(cat)}
                      </div>
                      <div className="category-bar-group">
                        <div className="progress-track">
                          <div
                            className={`progress-fill ${cat === 'TRANSIENT_INFRA' ? 'fill-warning' : 'fill-danger'}`}
                            style={{ width: `${percent}%` }}
                          ></div>
                        </div>
                        <span className="category-count">
                          {count} ({percent.toFixed(1)}%)
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Códigos de Error y Tipos Afectados */}
            <div className="error-details-section">
              <div className="error-table-card">
                <h4 className="section-title">Incidencias por Código</h4>
                <div className="tags-cloud">
                  {codes.map(([code, count]) => (
                    <div key={code} className="error-tag-item">
                      <code className="error-code-label">{code}</code>
                      <span className="error-count-badge">{count}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="error-table-card" style={{ marginTop: '12px' }}>
                <h4 className="section-title">Fallos por Dominio</h4>
                <div className="tags-cloud">
                  {jobTypes.map(([jType, count]) => (
                    <div key={jType} className="error-tag-item">
                      <span className="job-type-label">{jType}</span>
                      <span className="error-count-badge">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ErrorTaxonomyMatrix;
