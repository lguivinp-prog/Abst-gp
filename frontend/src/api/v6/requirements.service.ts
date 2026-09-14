import { v6Client } from './v6Client';
import type { RequirementResponse, RequirementCreate, RequirementUpdate } from './requirements.types';
import { handleApiError } from '../apiError';

export const requirementsPaths = {
  list: (caseId: string | number) => `/cases/${caseId}/requirements`,
  detail: (caseId: string | number, reqId: string | number) => `/cases/${caseId}/requirements/${reqId}`,
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
  }
};
