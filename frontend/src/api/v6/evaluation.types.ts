export interface EvaluationResponse {
  id: number;
  supplier_offer_id: number;
  requirement_id: number;
  status: string;
  explanation?: string;
  evaluation_confidence?: number;
  requirement_description?: string;
  requirement_type?: string;
}

export interface EvaluationUpdate {
  status: string;
  explanation: string;
}

export interface RequirementEvidenceResponse {
  id: number;
  case_id: number;
  supplier_offer_id: number;
  requirement_id: number;
  offer_evidence_id: number;
  document_id?: number | null;
  source_document?: string | null;
  page?: number | null;
  fragment?: string | null;
  verification_status: 'PENDING' | 'VERIFIED' | 'REJECTED' | 'OBSERVED' | string;
  verified_by?: number | null;
  verified_by_username?: string | null;
  verified_at?: string | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RequirementEvidenceReview {
  verification_status: 'VERIFIED' | 'REJECTED' | 'OBSERVED' | 'PENDING';
  notes?: string;
}

export interface RequirementEvidenceCreate {
  offer_evidence_id: number;
  document_id?: number;
  source_document?: string;
  page?: number;
  fragment?: string;
  notes?: string;
}
