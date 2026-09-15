import type { SupplierBasic } from './supplier.types';

export interface SupplierOfferResponse {
  id: number;
  case_id: number;
  supplier_id: number;
  status: string;
  evaluation_status: string;
  price?: number;
  source_document?: string;
  supplier?: SupplierBasic;
}

export interface SupplierOfferCreate {
  supplier_id: number;
  price?: number;
  source_document?: string;
}

export interface SupplierOfferUpdate {
  price?: number;
  source_document?: string;
  status?: string;
}
