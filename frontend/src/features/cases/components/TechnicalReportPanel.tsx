import React, { useState, useEffect } from 'react';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { useAuth } from '../../auth/AuthContext';
import { reportsService } from '../../../api/v6/reports.service';
import type {
  TechnicalReportSummary,
  TechnicalReportDetail,
  ReportIntegrityCheckResponse,
} from '../../../api/v6/reports.types';
import {
  FileText,
  ShieldCheck,
  AlertCircle,
  CheckCircle2,
  Clock,
  XCircle,
  Download,
  Eye,
  RefreshCw,
  Lock,
  AlertTriangle,
  X,
} from 'lucide-react';
import './TechnicalReportPanel.css';

interface TechnicalReportPanelProps {
  caseId: string;
  caseStatus?: string;
  onRefresh?: () => void;
}

export const TechnicalReportPanel: React.FC<TechnicalReportPanelProps> = ({
  caseId,
  caseStatus,
  onRefresh,
}) => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [reports, setReports] = useState<TechnicalReportSummary[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [reportDetail, setReportDetail] = useState<TechnicalReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modals state
  const [showApproveModal, setShowApproveModal] = useState(false);
  const [approvalNotes, setApprovalNotes] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [integrityResult, setIntegrityResult] = useState<ReportIntegrityCheckResponse | null>(null);

  // RBAC & SoD flags
  const canApproveRole = user?.role === 'SUPERVISOR' || user?.role === 'ADMIN';
  const isAuthor = Boolean(
    reportDetail && user && user.id && (user.id === reportDetail.generated_by || String(user.id) === String(reportDetail.generated_by))
  );
  const isCaseApproved = caseStatus === 'APPROVED';

  const loadReports = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await reportsService.listReports(caseId);
      const list = resp.reports || [];
      setReports(list);
      if (list.length > 0) {
        // Select latest or currently selected
        const current = selectedReportId
          ? list.find((r) => r.id === selectedReportId) || list[0]
          : list[0];
        setSelectedReportId(current.id);
        await loadDetail(current.id);
      } else {
        setSelectedReportId(null);
        setReportDetail(null);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al listar informes técnicos');
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (reportId: number) => {
    try {
      const detail = await reportsService.getReport(reportId);
      setReportDetail(detail);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al obtener detalle del informe');
    }
  };

  useEffect(() => {
    loadReports();
  }, [caseId]);

  const handleSelectReport = (reportId: number) => {
    setSelectedReportId(reportId);
    loadDetail(reportId);
  };

  const handleGenerate = async () => {
    setActionLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const created = await reportsService.generateReport(caseId);
      setSuccessMsg(`Informe técnico v${created.version_number} generado exitosamente.`);
      await loadReports();
      setSelectedReportId(created.id);
      setReportDetail(created);
      if (onRefresh) onRefresh();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al generar informe técnico');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmitReview = async () => {
    if (!selectedReportId) return;
    setActionLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const updated = await reportsService.submitForReview(selectedReportId);
      setSuccessMsg(`Informe técnico v${updated.version_number} enviado a revisión formal.`);
      await loadReports();
      setReportDetail(updated);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al enviar a revisión');
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!selectedReportId) return;
    setActionLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const updated = await reportsService.approveReport(selectedReportId, {
        approval_notes: approvalNotes.trim() || undefined,
      });
      setShowApproveModal(false);
      setApprovalNotes('');
      setSuccessMsg(`Informe técnico v${updated.version_number} aprobado formalmente y PDF certificado generado.`);
      await loadReports();
      setReportDetail(updated);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al aprobar informe');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!selectedReportId || !rejectionReason.trim()) {
      setError('El motivo del rechazo es obligatorio para la subsanación técnica.');
      return;
    }
    setActionLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const updated = await reportsService.rejectReport(selectedReportId, {
        rejection_reason: rejectionReason.trim(),
      });
      setShowRejectModal(false);
      setRejectionReason('');
      setSuccessMsg(`Informe técnico v${updated.version_number} rechazado con observaciones registradas.`);
      await loadReports();
      setReportDetail(updated);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al rechazar informe');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!selectedReportId) return;
    setActionLoading(true);
    setError(null);
    try {
      const blob = await reportsService.getReportPdfBlob(selectedReportId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `informe-tecnico-evaluacion-v${reportDetail?.version_number || 1}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al descargar PDF certificado');
    } finally {
      setActionLoading(false);
    }
  };

  const handleViewHtml = async () => {
    if (!selectedReportId) return;
    setActionLoading(true);
    setError(null);
    try {
      const html = await reportsService.getReportHtml(selectedReportId);
      setPreviewHtml(html);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al cargar HTML del informe');
    } finally {
      setActionLoading(false);
    }
  };

  const handleVerifyIntegrity = async () => {
    if (!selectedReportId) return;
    setActionLoading(true);
    setError(null);
    try {
      const integrity = await reportsService.verifyIntegrity(selectedReportId);
      setIntegrityResult(integrity);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Error al verificar integridad criptográfica');
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'GENERATED':
        return <Badge variant="secondary">Borrador (Generado)</Badge>;
      case 'UNDER_REVIEW':
        return <Badge variant="warning">En Revisión Formal</Badge>;
      case 'APPROVED':
        return <Badge variant="success">Aprobado y Certificado</Badge>;
      case 'REJECTED':
        return <Badge variant="danger">Rechazado con Observaciones</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  if (loading) {
    return (
      <div className="tech-report-panel">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <RefreshCw className="animate-spin" size={16} />
          <span>Cargando informes técnicos...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="tech-report-panel">
      {/* HEADER */}
      <div className="tech-report-header">
        <div>
          <div className="tech-report-title">
            <FileText size={20} className="text-blue-600" />
            <span>Informe Técnico de Evaluación y Selección (P13)</span>
          </div>
          <p className="tech-report-subtitle">
            Documentación formal, auditable y congelada con verificación criptográfica de 3 dominios (Snapshot, HTML, PDF).
          </p>
        </div>

        {isCaseApproved && (
          <Button
            onClick={handleGenerate}
            disabled={actionLoading}
            variant="primary"
            className="flex items-center gap-1 text-xs"
          >
            <RefreshCw size={14} className={actionLoading ? 'animate-spin' : ''} />
            <span>Generar Nuevo Informe (v{(reports[0]?.version_number || 0) + 1})</span>
          </Button>
        )}
      </div>

      {/* ALERTS */}
      {!isCaseApproved && (
        <div className="tech-report-alert tech-report-alert-warning">
          <AlertTriangle size={18} />
          <span>
            <strong>Prerrequisito Administrativo:</strong> La generación del Informe Técnico requiere que la selección del expediente haya sido aprobada formalmente.
          </span>
        </div>
      )}

      {error && (
        <div className="tech-report-alert tech-report-alert-error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {successMsg && (
        <div className="tech-report-alert tech-report-alert-success">
          <CheckCircle2 size={18} />
          <span>{successMsg}</span>
        </div>
      )}

      {/* VERSIONS SELECTOR */}
      {reports.length > 0 ? (
        <>
          <div className="tech-report-list">
            {reports.map((r) => (
              <button
                key={r.id}
                onClick={() => handleSelectReport(r.id)}
                className={`tech-report-tab ${r.id === selectedReportId ? 'active' : ''}`}
              >
                <span>Versión {r.version_number}</span>
                {getStatusBadge(r.status)}
              </button>
            ))}
          </div>

          {/* ACTIVE REPORT DETAIL */}
          {reportDetail && (
            <div className="tech-report-card">
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-bold text-gray-900 text-sm flex items-center gap-2">
                  <ShieldCheck size={18} className="text-blue-600" />
                  Informe Técnico — Versión {reportDetail.version_number}
                </h4>
                {getStatusBadge(reportDetail.status)}
              </div>

              <div className="tech-report-grid">
                <div>
                  <div className="tech-report-field-label">Generado Por</div>
                  <div className="tech-report-field-value">
                    Usuario #{reportDetail.generated_by || 'Sistema'}
                  </div>
                </div>
                <div>
                  <div className="tech-report-field-label">Fecha de Generación</div>
                  <div className="tech-report-field-value">
                    {reportDetail.generated_at
                      ? new Date(reportDetail.generated_at).toLocaleString('es-PE')
                      : 'N/A'}
                  </div>
                </div>

                {reportDetail.status === 'APPROVED' && (
                  <>
                    <div>
                      <div className="tech-report-field-label">Aprobado Por</div>
                      <div className="tech-report-field-value">
                        Usuario #{reportDetail.approved_by || 'Supervisor'}
                      </div>
                    </div>
                    <div>
                      <div className="tech-report-field-label">Fecha de Aprobación</div>
                      <div className="tech-report-field-value">
                        {reportDetail.approved_at
                          ? new Date(reportDetail.approved_at).toLocaleString('es-PE')
                          : 'N/A'}
                      </div>
                    </div>
                  </>
                )}

                {reportDetail.status === 'REJECTED' && (
                  <>
                    <div>
                      <div className="tech-report-field-label">Rechazado Por</div>
                      <div className="tech-report-field-value">
                        Usuario #{reportDetail.rejected_by || 'Supervisor'}
                      </div>
                    </div>
                    <div>
                      <div className="tech-report-field-label">Fecha de Rechazo</div>
                      <div className="tech-report-field-value">
                        {reportDetail.rejected_at
                          ? new Date(reportDetail.rejected_at).toLocaleString('es-PE')
                          : 'N/A'}
                      </div>
                    </div>
                  </>
                )}
              </div>

              {/* REJECTION REASON BANNER */}
              {reportDetail.status === 'REJECTED' && reportDetail.rejection_reason && (
                <div className="tech-report-alert tech-report-alert-error mt-2 mb-2">
                  <XCircle size={18} />
                  <div>
                    <strong>Observaciones de Rechazo:</strong>
                    <p className="mt-1">{reportDetail.rejection_reason}</p>
                    <p className="mt-1 text-xs text-gray-600">
                      Subsanadas las observaciones, genere una nueva versión del informe.
                    </p>
                  </div>
                </div>
              )}

              {/* APPROVAL NOTES */}
              {reportDetail.status === 'APPROVED' && reportDetail.approval_notes && (
                <div className="tech-report-alert tech-report-alert-info mt-2 mb-2">
                  <CheckCircle2 size={18} />
                  <div>
                    <strong>Notas de Aprobación:</strong>
                    <p className="mt-1">{reportDetail.approval_notes}</p>
                  </div>
                </div>
              )}

              {/* CRYPTOGRAPHIC HASHES */}
              <div className="tech-report-hashes">
                <div className="font-semibold text-gray-700 mb-1 flex items-center gap-1">
                  <Lock size={13} /> Integridad Criptográfica de 3 Dominios (SHA-256)
                </div>
                <div className="tech-report-hash-row">
                  <span className="text-gray-500">Snapshot Canónico:</span>
                  <span className="font-mono text-gray-800">
                    {reportDetail.snapshot_hash || 'Pendiente de generación'}
                  </span>
                </div>
                <div className="tech-report-hash-row">
                  <span className="text-gray-500">HTML Congelado:</span>
                  <span className="font-mono text-gray-800">
                    {reportDetail.html_hash || 'Pendiente de aprobación'}
                  </span>
                </div>
                <div className="tech-report-hash-row">
                  <span className="text-gray-500">PDF Final:</span>
                  <span className="font-mono text-gray-800">
                    {reportDetail.pdf_hash || 'Pendiente de certificación'}
                  </span>
                </div>
              </div>

              {/* SoD WARNING IF USER IS AUTHOR */}
              {reportDetail.status === 'UNDER_REVIEW' && isAuthor && (
                <div className="tech-report-alert tech-report-alert-warning mt-3">
                  <AlertTriangle size={18} />
                  <span>
                    <strong>Separación de Funciones (SoD):</strong> Usted es el autor que generó este informe técnico. La normativa y controles del sistema prohíben la autoaprobación o autorechazo. Un evaluador o supervisor independiente debe realizar la revisión.
                  </span>
                </div>
              )}

              {/* ACTION BUTTONS */}
              <div className="tech-report-actions">
                {/* DRAFT -> SUBMIT */}
                {reportDetail.status === 'GENERATED' && (
                  <Button
                    onClick={handleSubmitReview}
                    disabled={actionLoading}
                    variant="primary"
                    className="flex items-center gap-1 text-xs"
                  >
                    <Clock size={14} />
                    <span>Enviar a Revisión Formal</span>
                  </Button>
                )}

                {/* UNDER_REVIEW -> APPROVE / REJECT */}
                {reportDetail.status === 'UNDER_REVIEW' && canApproveRole && !isAuthor && (
                  <>
                    <Button
                      onClick={() => setShowApproveModal(true)}
                      disabled={actionLoading}
                      variant="primary"
                      className="flex items-center gap-1 text-xs bg-emerald-600 hover:bg-emerald-700"
                    >
                      <ShieldCheck size={14} />
                      <span>Aprobar Informe</span>
                    </Button>

                    <Button
                      onClick={() => setShowRejectModal(true)}
                      disabled={actionLoading}
                      variant="secondary"
                      className="flex items-center gap-1 text-xs text-red-600 hover:text-red-700"
                    >
                      <XCircle size={14} />
                      <span>Rechazar con Observaciones</span>
                    </Button>
                  </>
                )}

                {/* VIEW HTML */}
                <Button
                  onClick={handleViewHtml}
                  disabled={actionLoading}
                  variant="secondary"
                  className="flex items-center gap-1 text-xs"
                >
                  <Eye size={14} />
                  <span>Ver Vista Previa HTML</span>
                </Button>

                {/* DOWNLOAD PDF (APPROVED ONLY) */}
                {reportDetail.status === 'APPROVED' && reportDetail.has_pdf && (
                  <Button
                    onClick={handleDownloadPdf}
                    disabled={actionLoading}
                    variant="primary"
                    className="flex items-center gap-1 text-xs"
                  >
                    <Download size={14} />
                    <span>Descargar PDF Certificado</span>
                  </Button>
                )}

                {/* VERIFY INTEGRITY */}
                <Button
                  onClick={handleVerifyIntegrity}
                  disabled={actionLoading}
                  variant="secondary"
                  className="flex items-center gap-1 text-xs"
                >
                  <Lock size={14} />
                  <span>Verificar Autenticidad</span>
                </Button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-6 text-sm text-gray-500 bg-gray-50 rounded border border-dashed border-gray-200">
          <p className="font-medium text-gray-700">No se ha emitido ningún informe técnico todavía.</p>
          <p className="text-xs text-gray-500 mt-1">
            {isCaseApproved
              ? 'Haga clic en "Generar Nuevo Informe" para crear el primer borrador oficial.'
              : 'Apruebe la selección en este expediente para habilitar la emisión del informe técnico.'}
          </p>
        </div>
      )}

      {/* ISOLATED HTML PREVIEW MODAL */}
      {previewHtml && (
        <div className="tech-report-modal-overlay">
          <div className="tech-report-modal">
            <div className="tech-report-modal-header">
              <h3 className="font-bold text-sm text-gray-800 flex items-center gap-2">
                <Eye size={16} /> Vista Previa Aislada del Informe Técnico (v{reportDetail?.version_number})
              </h3>
              <button
                onClick={() => setPreviewHtml(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>
            <div className="tech-report-modal-body">
              <iframe
                title="Preview Informe Técnico"
                className="tech-report-preview-iframe"
                sandbox=""
                srcDoc={previewHtml}
              />
            </div>
          </div>
        </div>
      )}

      {/* APPROVE MODAL */}
      {showApproveModal && (
        <div className="tech-report-modal-overlay">
          <div className="tech-report-modal" style={{ maxWidth: '500px' }}>
            <div className="tech-report-modal-header">
              <h3 className="font-bold text-sm text-emerald-800 flex items-center gap-2">
                <ShieldCheck size={18} /> Aprobar Informe Técnico (v{reportDetail?.version_number})
              </h3>
              <button
                onClick={() => setShowApproveModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>
            <div className="tech-report-modal-body">
              <p className="text-xs text-gray-600 mb-3">
                Al certificar este informe, se congelará el HTML definitivo con los datos de aprobación, se generará el PDF firmado en ReportLab y se sellarán sus hashes criptográficos.
              </p>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Notas de Aprobación (Opcional):
              </label>
              <textarea
                value={approvalNotes}
                onChange={(e) => setApprovalNotes(e.target.value)}
                placeholder="Ejemplo: Se certifica la conformidad del procedimiento y el cumplimiento estricto del orden de prelación."
                className="w-full text-xs p-2 border border-gray-300 rounded focus:ring-1 focus:ring-blue-500"
                rows={3}
              />
              <div className="flex justify-end gap-2 mt-4">
                <Button
                  onClick={() => setShowApproveModal(false)}
                  disabled={actionLoading}
                  variant="secondary"
                  className="text-xs"
                >
                  Cancelar
                </Button>
                <Button
                  onClick={handleApprove}
                  disabled={actionLoading}
                  variant="primary"
                  className="text-xs bg-emerald-600 hover:bg-emerald-700"
                >
                  Confirmar Aprobación
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* REJECT MODAL */}
      {showRejectModal && (
        <div className="tech-report-modal-overlay">
          <div className="tech-report-modal" style={{ maxWidth: '500px' }}>
            <div className="tech-report-modal-header">
              <h3 className="font-bold text-sm text-red-800 flex items-center gap-2">
                <XCircle size={18} /> Rechazar Informe Técnico (v{reportDetail?.version_number})
              </h3>
              <button
                onClick={() => setShowRejectModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>
            <div className="tech-report-modal-body">
              <p className="text-xs text-gray-600 mb-3">
                Indique las observaciones técnicas o formales que impiden la aprobación del informe. El informe pasará al estado REJECTED y quedará disponible para subsanación.
              </p>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Motivo de Rechazo (Obligatorio):
              </label>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Detalle de observaciones para subsanación técnica..."
                className="w-full text-xs p-2 border border-gray-300 rounded focus:ring-1 focus:ring-red-500"
                rows={3}
                required
              />
              <div className="flex justify-end gap-2 mt-4">
                <Button
                  onClick={() => setShowRejectModal(false)}
                  disabled={actionLoading}
                  variant="secondary"
                  className="text-xs"
                >
                  Cancelar
                </Button>
                <Button
                  onClick={handleReject}
                  disabled={actionLoading || !rejectionReason.trim()}
                  variant="primary"
                  className="text-xs bg-red-600 hover:bg-red-700"
                >
                  Confirmar Rechazo
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* INTEGRITY RESULT MODAL */}
      {integrityResult && (
        <div className="tech-report-modal-overlay">
          <div className="tech-report-modal" style={{ maxWidth: '550px' }}>
            <div className="tech-report-modal-header">
              <h3 className="font-bold text-sm text-gray-900 flex items-center gap-2">
                <Lock size={16} /> Certificación Criptográfica de Autenticidad
              </h3>
              <button
                onClick={() => setIntegrityResult(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X size={20} />
              </button>
            </div>
            <div className="tech-report-modal-body text-xs">
              <div
                className={`p-3 rounded mb-3 flex items-center gap-2 font-medium ${
                  integrityResult.is_authentic
                    ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                    : 'bg-red-50 text-red-800 border border-red-200'
                }`}
              >
                {integrityResult.is_authentic ? (
                  <CheckCircle2 size={18} className="text-emerald-600" />
                ) : (
                  <AlertCircle size={18} className="text-red-600" />
                )}
                <span>
                  {integrityResult.is_authentic
                    ? 'Autenticidad Criptográfica Verificada: Documento íntegro sin alteraciones.'
                    : 'Fallo de Verificación de Integridad: El documento o sus firmas presentan discrepancias.'}
                </span>
              </div>

              <div className="space-y-2 bg-gray-50 p-3 rounded border border-gray-200">
                <div className="flex justify-between items-center">
                  <span>1. Snapshot Canónico Certificado:</span>
                  <span className="font-semibold text-emerald-700">
                    {integrityResult.snapshot_hash_matches ? '✓ Coincide' : '✗ Discrepancia'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span>2. HTML Congelado Aprobado:</span>
                  <span className="font-semibold text-emerald-700">
                    {integrityResult.html_hash_matches ? '✓ Coincide' : '✗ Discrepancia'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span>3. Archivo PDF Físico y Hash:</span>
                  <span className="font-semibold text-emerald-700">
                    {integrityResult.pdf_hash_matches ? '✓ Coincide' : '✗ Discrepancia'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span>4. Presencia Física del Artefacto PDF:</span>
                  <span className="font-semibold text-emerald-700">
                    {integrityResult.pdf_file_exists ? '✓ Almacenado' : '✗ No encontrado'}
                  </span>
                </div>
              </div>

              <p className="mt-3 text-gray-500 text-[11px] leading-relaxed">
                {integrityResult.details}
              </p>

              <div className="flex justify-end mt-4">
                <Button
                  onClick={() => setIntegrityResult(null)}
                  variant="secondary"
                  className="text-xs"
                >
                  Cerrar
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
