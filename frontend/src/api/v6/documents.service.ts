import { v6Client } from './v6Client';
import type { DocumentResponse } from './documents.types';
import { handleApiError } from '../apiError';

export const documentsPaths = {
  list: (caseId: string | number) => `/cases/${caseId}/documents`,
};

export const documentsService = {
  getDocuments: async (caseId: string): Promise<DocumentResponse[]> => {
    try {
      return await v6Client.get<DocumentResponse[]>(documentsPaths.list(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  },
  getDocumentContent: async (caseId: string, documentId: number): Promise<Blob> => {
    try {
      // @ts-ignore
      return await v6Client.get<Blob>(`/cases/${caseId}/documents/${documentId}/content`, { responseType: 'blob' });
    } catch (error) {
      throw handleApiError(error);
    }
  }
};
