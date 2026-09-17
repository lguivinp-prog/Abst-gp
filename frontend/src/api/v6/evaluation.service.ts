import { v6Client } from './v6Client';
import type { EvaluationResponse, EvaluationUpdate } from './evaluation.types';
import { handleApiError } from '../apiError';

export const evaluationPaths = {
  list: (caseId: string | number) => `/cases/${caseId}/evaluations`,
  offerList: (caseId: string | number, offerId: string | number) => `/cases/${caseId}/offers/${offerId}/evaluations`,
  evaluate: (caseId: string | number, offerId: string | number) => `/cases/${caseId}/offers/${offerId}/evaluate`,
  update: (caseId: string | number, evalId: string | number) => `/cases/${caseId}/evaluations/${evalId}`,
  contractualList: (caseId: string | number) => `/cases/${caseId}/evaluations/contractual`,
  vfm: (caseId: string | number) => `/cases/${caseId}/evaluations/vfm`,
};

export const evaluationService = {
  getCaseEvaluations: async (caseId: string): Promise<EvaluationResponse[]> => {
    try {
      return await v6Client.get<EvaluationResponse[]>(evaluationPaths.list(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getOfferEvaluations: async (caseId: string, offerId: number): Promise<EvaluationResponse[]> => {
    try {
      return await v6Client.get<EvaluationResponse[]>(evaluationPaths.offerList(caseId, offerId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  evaluateOffer: async (caseId: string, offerId: number): Promise<EvaluationResponse[]> => {
    try {
      return await v6Client.post<EvaluationResponse[], void>(evaluationPaths.evaluate(caseId, offerId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  updateEvaluation: async (caseId: string, evalId: number, data: EvaluationUpdate): Promise<EvaluationResponse> => {
    try {
      return await v6Client.put<EvaluationResponse, EvaluationUpdate>(evaluationPaths.update(caseId, evalId), data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getContractualEvaluations: async (caseId: string): Promise<any[]> => {
    try {
      return await v6Client.get<any[]>(evaluationPaths.contractualList(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  getVFMRanking: async (caseId: string): Promise<any[]> => {
    try {
      return await v6Client.get<any[]>(evaluationPaths.vfm(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  }
};
