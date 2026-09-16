import type { SupplierBasic } from './supplier.types';

export type NumericLike = number | string;

export interface SupplierOfferItemCreate {
  procurement_item_id: number;
  unit_price: NumericLike;
}

export interface SupplierOfferItemResponse {
  id: number;
  procurement_item_id: number;
  description?: string;
  quantity: NumericLike;
  unit: string;
  unit_price: NumericLike;
  subtotal: NumericLike;
}

export interface SupplierOfferResponse {
  id: number;
  case_id: number;
  supplier_id: number;
  status: string;
  evaluation_status: string;
  price?: NumericLike;
  currency?: string;
  source_document?: string;
  documents?: any[];
  supplier?: SupplierBasic;
  items?: SupplierOfferItemResponse[];
  total_amount?: NumericLike;
}

export interface SupplierOfferCreate {
  supplier_id: number;
  price?: NumericLike;
  currency?: string;
  source_document?: string;
  document_ids?: number[];
  items?: SupplierOfferItemCreate[];
}

export interface SupplierOfferUpdate {
  price?: NumericLike;
  currency?: string;
  source_document?: string;
  status?: string;
  document_ids?: number[];
  items?: SupplierOfferItemCreate[];
}
