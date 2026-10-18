export type TechnicalReportStatus = 'GENERATED' | 'UNDER_REVIEW' | 'APPROVED' | 'REJECTED';

export interface TechnicalReportSummary {
  id: number;
  case_id: number | string;
  report_kind: string;
  version_number: number;
  status: TechnicalReportStatus;
  generated_by: number | null;
  generated_at: string;
  approved_by: number | null;
  approved_at: string | null;
  rejected_by: number | null;
  rejected_at: string | null;
  snapshot_hash: string | null;
  html_hash: string | null;
  pdf_hash: string | null;
  has_pdf: boolean;
}

export interface TechnicalReportDetail extends TechnicalReportSummary {
  approval_notes: string | null;
  rejection_reason: string | null;
  idempotency_key: string | null;
  request_hash?: string | null;
  source_snapshot: Record<string, any> | null;
  snapshot_payload?: Record<string, any> | null; // Alias de compatibilidad
}

export interface TechnicalReportListResponse {
  reports: TechnicalReportSummary[];
  total: number;
  total_reports?: number; // Alias de compatibilidad
  case_id?: number | string;
}

export interface ReportIntegrityCheckResponse {
  report_id: number;
  status: string;
  snapshot_hash_stored?: string | null;
  snapshot_hash_recalculated?: string | null;
  snapshot_intact: boolean;
  html_hash_stored?: string | null;
  html_hash_recalculated?: string | null;
  html_intact: boolean;
  pdf_hash_stored?: string | null;
  pdf_hash_recalculated?: string | null;
  pdf_file_exists: boolean;
  pdf_intact: boolean;
  is_authentic: boolean;
  details?: string | null;

  // Aliases de compatibilidad con UI y pruebas
  snapshot_hash_matches?: boolean;
  html_hash_matches?: boolean;
  pdf_hash_matches?: boolean;
  has_canonical_snapshot?: boolean;
}

export interface ReportGenerateRequest {
  idempotency_key?: string;
  template_version?: string;
}

export interface ReportApproveRequest {
  approval_notes?: string;
}

export interface ReportRejectRequest {
  rejection_reason: string;
}
