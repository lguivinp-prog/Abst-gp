import React from 'react';
import { Activity, RefreshCw, AlertTriangle, Play, Pause, Clock } from 'lucide-react';
import useSREMonitoring from '../../hooks/useSREMonitoring';
import WorkerClusterStatus from './WorkerClusterStatus';
import LatencySLACards from './LatencySLACards';
import ErrorTaxonomyMatrix from './ErrorTaxonomyMatrix';
import RecoveryControlPanel from './RecoveryControlPanel';
import './MonitoringDashboard.css';

export const MonitoringDashboard: React.FC = () => {
  const {
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
    refetch,
    triggerRecovery,
    isTriggeringRecovery,
    lastRecoveryResult,
  } = useSREMonitoring({
    pollingIntervalMs: 10000,
    initialTimeWindowHours: 24,
    autoRefreshEnabled: true,
  });

  return (
    <div className="sre-dashboard-container">
      {/* Top Header & Global Controls */}
      <header className="sre-dashboard-header">
        <div className="sre-header-left">
          <div className="sre-header-icon">
            <Activity size={28} />
          </div>
          <div className="sre-header-titles">
            <h1>Centro de Observabilidad & SRE</h1>
            <p>
              Telemetría en tiempo real, SLAs, salud del cluster de workers y recuperación automática V5.4
            </p>
          </div>
        </div>

        <div className="sre-header-actions">
          {lastUpdated && (
            <span className="last-updated-text">
              <Clock size={14} />
              Actualizado: {lastUpdated.toLocaleTimeString()}
            </span>
          )}

          <button
            type="button"
            className={`btn-toggle-refresh ${isAutoRefreshActive ? 'active' : ''}`}
            onClick={toggleAutoRefresh}
            title={isAutoRefreshActive ? 'Pausar auto-refresco cada 10s' : 'Activar auto-refresco cada 10s'}
          >
            {isAutoRefreshActive ? (
              <>
                <Pause size={14} />
                Auto-refresh (10s)
              </>
            ) : (
              <>
                <Play size={14} />
                Pausado
              </>
            )}
          </button>

          <button
            type="button"
            className="btn-refetch"
            onClick={() => refetch()}
            disabled={isLoading || isRefreshing}
          >
            <RefreshCw size={14} className={isRefreshing ? 'spin' : ''} />
            {isRefreshing ? 'Actualizando...' : 'Refrescar'}
          </button>
        </div>
      </header>

      {/* Error Alert Banner */}
      {error && (
        <div className="sre-error-banner" role="alert">
          <AlertTriangle size={20} />
          <span><strong>Error de telemetría:</strong> {error}</span>
        </div>
      )}

      {/* 1. Worker Health & Cluster Status */}
      <WorkerClusterStatus data={workersData} isLoading={isLoading} />

      {/* 2. Latency Metrics & SLA Percentiles */}
      <LatencySLACards
        data={latencyData}
        isLoading={isLoading}
        timeWindowHours={timeWindowHours}
        onTimeWindowChange={setTimeWindowHours}
        jobTypeFilter={jobTypeFilter}
        onJobTypeFilterChange={setJobTypeFilter}
      />

      {/* 3. Error Taxonomy & Failure Analytics */}
      <ErrorTaxonomyMatrix data={errorData} isLoading={isLoading} />

      {/* 4. Resilience & Recovery Engine Control */}
      <RecoveryControlPanel
        data={recoveryData}
        isLoading={isLoading}
        onTriggerRecovery={triggerRecovery}
        isTriggering={isTriggeringRecovery}
        lastResult={lastRecoveryResult}
      />
    </div>
  );
};

export default MonitoringDashboard;
