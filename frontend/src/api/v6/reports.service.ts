import { v6Client } from './v6Client';
import type {
  TechnicalReportDetail,
  TechnicalReportListResponse,
  ReportIntegrityCheckResponse,
  ReportGenerateRequest,
  ReportApproveRequest,
  ReportRejectRequest,
} from './reports.types';

export const reportsService = {
  generateReport: async (caseId: string, data?: ReportGenerateRequest): Promise<TechnicalReportDetail> => {
    return v6Client.post<TechnicalReportDetail>(
      `/reports/p13/cases/${caseId}/generate`,
      data || {}
    );
  },

  listReports: async (caseId: string): Promise<TechnicalReportListResponse> => {
    return v6Client.get<TechnicalReportListResponse>(`/reports/p13/cases/${caseId}/reports`);
  },

  getReport: async (reportId: number): Promise<TechnicalReportDetail> => {
    return v6Client.get<TechnicalReportDetail>(`/reports/p13/reports/${reportId}`);
  },

  submitForReview: async (reportId: number): Promise<TechnicalReportDetail> => {
    return v6Client.post<TechnicalReportDetail>(`/reports/p13/reports/${reportId}/submit-review`);
  },

  approveReport: async (reportId: number, data?: ReportApproveRequest): Promise<TechnicalReportDetail> => {
    return v6Client.post<TechnicalReportDetail>(`/reports/p13/reports/${reportId}/approve`, data || {});
  },

  rejectReport: async (reportId: number, data: ReportRejectRequest): Promise<TechnicalReportDetail> => {
    return v6Client.post<TechnicalReportDetail>(`/reports/p13/reports/${reportId}/reject`, data);
  },

  getReportHtml: async (reportId: number): Promise<string> => {
    return v6Client.get<string>(`/reports/p13/reports/${reportId}/export/html`, {
      responseType: 'text',
      transformResponse: [(data) => data],
    });
  },

  getReportPdfBlob: async (reportId: number): Promise<Blob> => {
    return v6Client.get<Blob>(`/reports/p13/reports/${reportId}/export/pdf`, {
      responseType: 'blob',
    });
  },

  verifyIntegrity: async (reportId: number): Promise<ReportIntegrityCheckResponse> => {
    return v6Client.get<ReportIntegrityCheckResponse>(`/reports/p13/reports/${reportId}/integrity`);
  },
};
