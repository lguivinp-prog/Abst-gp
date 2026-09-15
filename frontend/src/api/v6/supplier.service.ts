import { v6Client } from './v6Client';
import type { CaseSupplierResponse, SupplierCreate } from './supplier.types';
import { handleApiError } from '../apiError';

export const supplierPaths = {
  list: (caseId: string | number) => `/cases/${caseId}/suppliers`,
  detail: (caseId: string | number, supplierId: string | number) => `/cases/${caseId}/suppliers/${supplierId}`,
};

export const supplierService = {
  getCaseSuppliers: async (caseId: string): Promise<CaseSupplierResponse[]> => {
    try {
      return await v6Client.get<CaseSupplierResponse[]>(supplierPaths.list(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  linkCaseSupplier: async (caseId: string, data: SupplierCreate): Promise<CaseSupplierResponse> => {
    try {
      return await v6Client.post<CaseSupplierResponse, SupplierCreate>(supplierPaths.list(caseId), data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  unlinkCaseSupplier: async (caseId: string, supplierId: number): Promise<void> => {
    try {
      await v6Client.delete<void>(supplierPaths.detail(caseId, supplierId));
    } catch (error) {
      throw handleApiError(error);
    }
  }
};
