export type UpdateRequirementStatus = 'VALIDATED' | 'MODIFIED_BY_USER' | 'OBSERVED' | 'REJECTED';

export interface EvidenceResponse {
  id: number;
  source_document: string;
  source_page?: number | null;
  source_fragment: string;
  confidence: number;
}

export interface RequirementResponse {
  id: number;
  case_id: number;
  requirement_type: string;
  description: string;
  value?: string | null;
  mandatory: boolean;
  status: string;
  source_document_id?: number;
  numeric_value?: number | null;
  unit?: string | null;
  comparator?: string | null;
  evidences: EvidenceResponse[];
}

export interface RequirementCreate {
  requirement_type: string;
  description: string;
  mandatory: boolean;
  value?: string | null;
}

export interface RequirementUpdate {
  status: UpdateRequirementStatus;
  description?: string | null;
  value?: string | null;
  numeric_value?: number | null;
  unit?: string | null;
  comparator?: string | null;
  reason: string;
}

export interface ExtractionRequest {
  document_id: number;
}
