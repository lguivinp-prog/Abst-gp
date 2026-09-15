import type { SupplierBasic } from './supplier.types';

export interface SupplierOfferResponse {
  id: number;
  case_id: number;
  supplier_id: number;
  status: string;
  evaluation_status: string;
  price?: number;
  currency?: string;
  source_document?: string;
  documents?: any[];
  supplier?: SupplierBasic;
}

export interface SupplierOfferCreate {
  supplier_id: number;
  price?: number;
  currency?: string;
  source_document?: string;
  document_ids?: number[];
}

export interface SupplierOfferUpdate {
  price?: number;
  currency?: string;
  source_document?: string;
  status?: string;
  document_ids?: number[];
}
