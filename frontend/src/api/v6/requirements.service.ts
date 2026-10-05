import { v6Client } from './v6Client';
import type { RequirementResponse, RequirementCreate, RequirementUpdate } from './requirements.types';
import { handleApiError } from '../apiError';

export const requirementsPaths = {
  list: (caseId: string | number) => `/cases/${caseId}/requirements`,
  detail: (caseId: string | number, reqId: string | number) => `/cases/${caseId}/requirements/${reqId}`,
  extract: (caseId: string | number) => `/cases/${caseId}/requirements/extract`,
  procurementItems: (caseId: string | number) => `/cases/${caseId}/procurement-items`,
  confirm: (caseId: string | number) => `/cases/${caseId}/requirements/confirm`,
};

export const requirementsService = {
  getRequirements: async (caseId: string): Promise<RequirementResponse[]> => {
    try {
      return await v6Client.get<RequirementResponse[]>(requirementsPaths.list(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  createRequirement: async (caseId: string, data: RequirementCreate): Promise<RequirementResponse> => {
    try {
      return await v6Client.post<RequirementResponse, RequirementCreate>(requirementsPaths.list(caseId), data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  updateRequirement: async (caseId: string, reqId: string | number, data: RequirementUpdate): Promise<RequirementResponse> => {
    try {
      return await v6Client.put<RequirementResponse, RequirementUpdate>(requirementsPaths.detail(caseId, reqId), data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  extractRequirements: async (caseId: string, documentId: number): Promise<RequirementResponse[]> => {
    try {
      return await v6Client.post<RequirementResponse[], { document_id: number }>(requirementsPaths.extract(caseId), { document_id: documentId });
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getProcurementItems: async (caseId: string): Promise<any[]> => {
    try {
      return await v6Client.get<any[]>(requirementsPaths.procurementItems(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  createProcurementItem: async (caseId: string, data: any): Promise<any> => {
    try {
      return await v6Client.post<any, any>(requirementsPaths.procurementItems(caseId), data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  updateProcurementItem: async (caseId: string, itemId: number, data: any): Promise<any> => {
    try {
      return await v6Client.put<any, any>(`${requirementsPaths.procurementItems(caseId)}/${itemId}`, data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  deleteProcurementItem: async (caseId: string, itemId: number): Promise<void> => {
    try {
      await v6Client.delete(`${requirementsPaths.procurementItems(caseId)}/${itemId}`);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  confirmRequirements: async (caseId: string): Promise<{ message: string, status: string }> => {
    try {
      return await v6Client.post<{ message: string, status: string }, {}>(requirementsPaths.confirm(caseId), {});
    } catch (error) {
      throw handleApiError(error);
    }
  }
};
