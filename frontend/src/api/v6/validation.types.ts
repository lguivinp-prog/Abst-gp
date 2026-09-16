export interface ValidationRequestCreate {
  source: string;
}

export type ManualValidationResult = "VALIDATED" | "REJECTED" | "REVIEW_REQUIRED";

export interface ValidationManualCreate {
  source: string;
  result: ManualValidationResult;
  observation: string;
  evidence_reference?: string;
}

export interface SupplierBasic {
  id: number;
  ruc: string;
  business_name: string;
}

export interface UserBasic {
  id: number;
  username?: string;
  full_name?: string;
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
  validation_mode?: string;
  manual_result?: string;
  manual_observation?: string;
  manual_evidence_reference?: string;
  verified_by_user_id?: number;
  verified_at?: string;
  verified_by_user?: UserBasic;
}
