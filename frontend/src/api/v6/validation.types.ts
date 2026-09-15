export interface ValidationRequestCreate {
  source: string;
}

export interface SupplierBasic {
  id: number;
  ruc: string;
  business_name: string;
}

export interface ValidationRequestResponse {
  id: number;
  supplier_id: number;
  source: string;
  status: string;
  requested_at: string;
  completed_at?: string;
  response_payload?: any;
  supplier?: SupplierBasic;
}
