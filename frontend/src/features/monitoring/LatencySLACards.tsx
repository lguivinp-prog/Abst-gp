import React from 'react';
import { Gauge, Clock, BarChart3, Filter } from 'lucide-react';
import type { LatencyReportResponse } from '../../types/monitoring';

interface LatencySLACardsProps {
  data: LatencyReportResponse | null;
  isLoading: boolean;
  timeWindowHours: number;
  onTimeWindowChange: (hours: number) => void;
  jobTypeFilter: string;
  onJobTypeFilterChange: (jobType: string) => void;
}

function formatLatency(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)} ms`;
  }
  return `${(ms / 1000).toFixed(2)} s`;
}

export const LatencySLACards: React.FC<LatencySLACardsProps> = ({
  data,
  isLoading,
  timeWindowHours,
  onTimeWindowChange,
  jobTypeFilter,
  onJobTypeFilterChange,
}) => {
  const global = data?.global_metrics;
  const byType = data?.metrics_by_job_type || [];

  return (
    <div className="sre-card">
      <div className="sre-card-header">
        <div className="sre-card-title">
          <Gauge size={20} className="title-icon text-info" />
          <h3>Métricas de Rendimiento & SLAs</h3>
        </div>

        <div className="sre-controls">
          <div className="control-group">
            <Filter size={14} className="control-icon" />
            <select
              className="sre-select"
              value={jobTypeFilter}
              onChange={(e) => onJobTypeFilterChange(e.target.value)}
              disabled={isLoading}
              aria-label="Filtrar por tipo de trabajo"
            >
              <option value="ALL">Todos los Jobs</option>
              <option value="OCR_PROCESSING">OCR Requerimiento</option>
              <option value="QUOTATION_EXTRACTION">Extracción Cotización</option>
              <option value="COMPARISON_EVALUATION">Comparación Normativa</option>
            </select>
          </div>

          <div className="control-group">
            <Clock size={14} className="control-icon" />
            <div className="time-window-buttons">
              {[1, 6, 24, 168].map((h) => (
                <button
                  key={h}
                  type="button"
                  className={`btn-time-window ${timeWindowHours === h ? 'active' : ''}`}
                  onClick={() => onTimeWindowChange(h)}
                  disabled={isLoading}
                >
                  {h === 168 ? '7d' : `${h}h`}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="sre-card-body">
        {isLoading && !data ? (
          <div className="sre-loading-placeholder">
            <div className="skeleton skeleton-grid" style={{ height: '120px' }}></div>
          </div>
        ) : (
          <>
            {/* KPI Cards Grid */}
            <div className="kpi-grid">
              <div className="kpi-card">
                <span className="kpi-label">p50 (Mediana)</span>
                <span className="kpi-value text-primary">
                  {global ? formatLatency(global.p50_ms) : '0 ms'}
                </span>
                <span className="kpi-subtitle">50% de las operaciones</span>
              </div>

              <div className="kpi-card">
                <span className="kpi-label">p95 (SLA Crítico)</span>
                <span className={`kpi-value ${global && global.p95_ms > 30000 ? 'text-warning' : 'text-info'}`}>
                  {global ? formatLatency(global.p95_ms) : '0 ms'}
                </span>
                <span className="kpi-subtitle">95% de las operaciones</span>
              </div>

              <div className="kpi-card">
                <span className="kpi-label">p99 (Cola Extrema)</span>
                <span className={`kpi-value ${global && global.p99_ms > 60000 ? 'text-danger' : 'text-purple'}`}>
                  {global ? formatLatency(global.p99_ms) : '0 ms'}
                </span>
                <span className="kpi-subtitle">1% peor caso</span>
              </div>

              <div className="kpi-card">
                <span className="kpi-label">Promedio Global</span>
                <span className="kpi-value">
                  {global ? formatLatency(global.avg_ms) : '0 ms'}
                </span>
                <span className="kpi-subtitle">
                  Min: {global ? formatLatency(global.min_ms) : '0 ms'} | Max: {global ? formatLatency(global.max_ms) : '0 ms'}
                </span>
              </div>
            </div>

            {/* Sub-table by Job Type */}
            {byType.length > 0 && (
              <div className="sre-table-wrapper">
                <div className="table-header-title">
                  <BarChart3 size={16} />
                  <h4>Desglose de Latencia por Dominio</h4>
                </div>
                <table className="sre-table">
                  <thead>
                    <tr>
                      <th>Tipo de Job</th>
                      <th>Muestras</th>
                      <th>p50</th>
                      <th>p95</th>
                      <th>p99</th>
                      <th>Promedio</th>
                      <th>Rango (Mín - Máx)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byType.map((item) => (
                      <tr key={item.job_type}>
                        <td>
                          <span className="job-type-pill">{item.job_type}</span>
                        </td>
                        <td>{item.sample_count}</td>
                        <td><strong>{formatLatency(item.p50_ms)}</strong></td>
                        <td className={item.p95_ms > 30000 ? 'text-warning' : ''}>
                          {formatLatency(item.p95_ms)}
                        </td>
                        <td className={item.p99_ms > 60000 ? 'text-danger' : ''}>
                          {formatLatency(item.p99_ms)}
                        </td>
                        <td>{formatLatency(item.avg_ms)}</td>
                        <td>{formatLatency(item.min_ms)} - {formatLatency(item.max_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default LatencySLACards;
