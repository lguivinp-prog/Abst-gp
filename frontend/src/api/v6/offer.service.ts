import { v6Client } from './v6Client';
import type { SupplierOfferResponse, SupplierOfferUpdate } from './offer.types';
import { handleApiError } from '../apiError';

export const offerPaths = {
  list: (caseId: string | number) => `/cases/${caseId}/offers`,
  detail: (caseId: string | number, offerId: string | number) => `/cases/${caseId}/offers/${offerId}`,
};

export const offerService = {
  getOffers: async (caseId: string): Promise<SupplierOfferResponse[]> => {
    try {
      return await v6Client.get<SupplierOfferResponse[]>(offerPaths.list(caseId));
    } catch (error) {
      throw handleApiError(error);
    }
  },

  updateOffer: async (caseId: string, offerId: number, data: SupplierOfferUpdate): Promise<SupplierOfferResponse> => {
    try {
      return await v6Client.put<SupplierOfferResponse, SupplierOfferUpdate>(offerPaths.detail(caseId, offerId), data);
    } catch (error) {
      throw handleApiError(error);
    }
  },

  deleteOffer: async (caseId: string, offerId: number): Promise<void> => {
    try {
      await v6Client.delete<void>(offerPaths.detail(caseId, offerId));
    } catch (error) {
      throw handleApiError(error);
    }
  }
};
