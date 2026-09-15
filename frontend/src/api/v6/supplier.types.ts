export interface CaseSupplierResponse {
  id: number;
  ruc: string;
  business_name: string;
  legal_representative?: string;
  dni?: string;
  contact_email?: string;
  status?: string;
}

export interface SupplierBasic {
  id: number;
  ruc: string;
  business_name: string;
}

export interface SupplierCreate {
  ruc: string;
  business_name: string;
  legal_representative?: string;
  dni?: string;
  contact_email?: string;
}
