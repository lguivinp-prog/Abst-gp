import React from 'react';
import { ShieldAlert, ShieldCheck, Clock, RefreshCw, CheckSquare, AlertCircle } from 'lucide-react';



export const ValidationStatusBadge: React.FC<{ status: string, requestedAt?: string, isManual?: boolean }> = ({ status, requestedAt, isManual }) => {
  if (isManual) {
    return (
      <span className="val-badge val-info">
        <CheckSquare size={14} /> MANUAL
      </span>
    );
  }

  if (status === 'VALIDATED' || status === 'PASSED') {
    return (
      <span className="val-badge val-success" title={requestedAt ? `Validado: ${requestedAt}` : ''}>
        <ShieldCheck size={14} /> ✓ Validado
      </span>
    );
  }
  if (status === 'REVIEW' || status === 'WARNING') {
    return (
      <span className="val-badge val-warning" title={requestedAt ? `Actualizado: ${requestedAt}` : ''}>
        <ShieldAlert size={14} /> ⚠ Revisión
      </span>
    );
  }
  if (status === 'INCOMPLETE' || status === 'NO_DISPONIBLE_API' || status === 'MANUAL_REQUIRED') {
    return (
      <span className="val-badge val-warning">
        <AlertCircle size={14} /> Incompleto
      </span>
    );
  }
  if (status === 'PENDING' || status === 'RUNNING') {
    return (
      <span className="val-badge val-secondary">
        <RefreshCw size={14} className="spin" /> Pendiente
      </span>
    );
  }
  if (status === 'ERROR' || status === 'BLOCKED') {
    return (
      <span className="val-badge val-danger">
        <ShieldAlert size={14} /> ! Error
      </span>
    );
  }

  return (
    <span className="val-badge val-secondary">
      <Clock size={14} /> Sin datos
    </span>
  );
};
