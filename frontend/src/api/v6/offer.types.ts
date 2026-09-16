import type { SupplierBasic } from './supplier.types';

export interface SupplierOfferItemCreate {
  procurement_item_id: number;
  unit_price: number;
}

export interface SupplierOfferItemResponse {
  id: number;
  procurement_item_id: number;
  description?: string;
  quantity: number;
  unit: string;
  unit_price: number;
  subtotal: number;
}

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
  items?: SupplierOfferItemResponse[];
  total_amount?: number;
}

export interface SupplierOfferCreate {
  supplier_id: number;
  price?: number;
  currency?: string;
  source_document?: string;
  document_ids?: number[];
  items?: SupplierOfferItemCreate[];
}

export interface SupplierOfferUpdate {
  price?: number;
  currency?: string;
  source_document?: string;
  status?: string;
  document_ids?: number[];
  items?: SupplierOfferItemCreate[];
}
