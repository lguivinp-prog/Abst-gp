import { v6Client } from './v6Client';
import type { ValidationRequestResponse, ValidationRequestCreate } from './validation.types';
import { handleApiError } from '../apiError';

export const validationPaths = {
  list: (caseId: string | number) => `/cases/${caseId}/validations`,
  detail: (caseId: string | number, reqId: string | number) => `/cases/${caseId}/validations/${reqId}`,
  create: (caseId: string | number, supplierId: string | number) => `/cases/${caseId}/suppliers/${supplierId}/validations`,
  createManual: (caseId: string | number, supplierId: string | number) => `/cases/${caseId}/suppliers/${supplierId}/validations/manual`,
};

export const validationService = {
  getValidations: async (caseId: string): Promise<ValidationRequestResponse[]> => {
    try {
      return await v6Client.get<ValidationRequestResponse[]>(validationPaths.list(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getValidation: async (caseId: string, reqId: number): Promise<ValidationRequestResponse> => {
    try {
      return await v6Client.get<ValidationRequestResponse>(validationPaths.detail(caseId, reqId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  createValidation: async (caseId: string, supplierId: number, data: ValidationRequestCreate): Promise<ValidationRequestResponse> => {
    try {
      return await v6Client.post<ValidationRequestResponse, ValidationRequestCreate>(validationPaths.create(caseId, supplierId), data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  createManualValidation: async (caseId: string, supplierId: number, data: import('./validation.types').ValidationManualCreate): Promise<ValidationRequestResponse> => {
    try {
      return await v6Client.post<ValidationRequestResponse, import('./validation.types').ValidationManualCreate>(validationPaths.createManual(caseId, supplierId), data);
    } catch (error) {
      throw handleApiError(error);
    }
  }
};
