import apiClient from './client';
import type { CaseCreate, Case, ProcessingJobResponse, QuotationUploadResponse, ComparisonRunResponse } from '../types';
import { handleApiError } from './apiError';
import { QUOTATION_UPLOAD_TIMEOUT_MS, COMPARISON_RUN_TIMEOUT_MS } from '../config/documentLimits';
import type { DocumentSection, ConditionComparison } from '../features/cases/domain/models';
import type { V1ParsedSectionDto, V1FinalConditionComparisonDto } from '../features/cases/adapters/v1Types';
import { mapV1SectionToDomain, mapV1ComparisonToDomain } from '../features/cases/adapters/v1Adapters';

export const casesService = {
  getCases: async (): Promise<Case[]> => {
    try {
      const response = await apiClient.get<Case[]>('/cases/');
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getCase: async (id: string): Promise<Case> => {
    try {
      const response = await apiClient.get<Case>(`/cases/${id}`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  createCase: async (data: CaseCreate): Promise<Case> => {
    try {
      const response = await apiClient.post<Case>('/cases/', data);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  uploadRequirement: async (id: string, file: File, documentType: string = 'requirement'): Promise<{ message: string, job_id: string }> => {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', documentType);
      const response = await apiClient.post(`/cases/${id}/requirement/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  uploadQuotation: async (id: string, file: File): Promise<QuotationUploadResponse> => {
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await apiClient.post<QuotationUploadResponse>(`/cases/${id}/quotation/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: QUOTATION_UPLOAD_TIMEOUT_MS,
      });
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getJobStatus: async (jobId: string, signal?: AbortSignal): Promise<ProcessingJobResponse> => {
    try {
      const response = await apiClient.get<ProcessingJobResponse>(`/cases/jobs/${jobId}`, { signal });
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getRequirementDocumentBlob: async (caseId: string, signal?: AbortSignal): Promise<Blob> => {
    try {
      const response = await apiClient.get(`/cases/${caseId}/documents/requirement/content`, {
        responseType: 'blob',
        signal,
      });
      // The backend returns application/pdf
      if (response.data.type !== 'application/pdf') {
        // Just a warning, we still return the blob, but browsers might fail to render
        console.warn('Received blob is not explicitly application/pdf', response.data.type);
      }
      return response.data;
    } catch (error: any) {
      if (error.response && error.response.data instanceof Blob && error.response.data.type === 'application/json') {
        // Handle case where HTTP error was returned as a JSON Blob due to responseType: 'blob'
        try {
          const text = await error.response.data.text();
          const json = JSON.parse(text);
          error.response.data = json; // Mutate response data back to JSON so handleApiError works normally
        } catch (e) {
          // Ignore parsing errors and let handleApiError do its default
        }
      }
      throw handleApiError(error);
    }
  },

  getSections: async (id: string): Promise<DocumentSection[]> => {
    try {
      const response = await apiClient.get<V1ParsedSectionDto[]>(`/cases/${id}/sections`);
      return response.data.map(mapV1SectionToDomain);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  updateSection: async (sectionId: string, data: { is_selected: boolean; review_status: string; current_text: string }): Promise<DocumentSection> => {
    try {
      const response = await apiClient.put<V1ParsedSectionDto>(`/cases/sections/${sectionId}`, data);
      return mapV1SectionToDomain(response.data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  confirmSections: async (id: string): Promise<Case> => {
    try {
      const response = await apiClient.post<Case>(`/cases/${id}/sections/confirm`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  runComparison: async (id: string, signal?: AbortSignal): Promise<ComparisonRunResponse> => {
    try {
      const response = await apiClient.post(`/cases/${id}/comparison/run`, undefined, {
        timeout: COMPARISON_RUN_TIMEOUT_MS,
        signal
      });
      return {
        message: response.data.message,
        job_id: response.data.job_id,
        status: response.data.status,
        alreadyCompleted: Boolean(response.data.already_completed),
        already_completed: Boolean(response.data.already_completed)
      };
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getComparison: async (id: string, signal?: AbortSignal): Promise<ConditionComparison[]> => {
    try {
      const response = await apiClient.get<V1FinalConditionComparisonDto[]>(`/cases/${id}/comparison`, { signal });
      return response.data.map((dto, idx) => mapV1ComparisonToDomain(dto, idx));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  generateHtml: async (id: string): Promise<{ message: string, version: number }> => {
    try {
      const response = await apiClient.post(`/cases/${id}/generate/html`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getOutput: async (id: string): Promise<{ html: string, plain_text: string, version: number }> => {
    try {
      const response = await apiClient.get(`/cases/${id}/output`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  // --- V6 methods ---
  getOffers: async (id: string): Promise<any[]> => {
    try {
      const response = await apiClient.get(`/api/v6/cases/${id}/offers`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getSelection: async (id: string): Promise<any> => {
    try {
      const response = await apiClient.get(`/api/v6/cases/${id}/selection`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  proposeSelection: async (id: string, data: { supplier_offer_id: number; justification_comment?: string }): Promise<any> => {
    try {
      const response = await apiClient.post(`/api/v6/cases/${id}/selection`, data);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getResult: async (id: string): Promise<any> => {
    try {
      const response = await apiClient.get(`/api/v6/cases/${id}/result`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  approveSelection: async (id: string): Promise<any> => {
    try {
      const response = await apiClient.post(`/api/v6/cases/${id}/approve`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getHistory: async (id: string): Promise<any[]> => {
    try {
      const response = await apiClient.get(`/api/v6/cases/${id}/history`);
      return response.data;
    } catch (error) {
      throw handleApiError(error);
    }
  },

};
