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
  category?: string | null;
  phase?: string | null;
  procurement_item_id?: number | null;
  flows_to_contract?: boolean;
  source_section?: string | null;
  key?: string | null;
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
  category?: string | null;
  phase?: string | null;
  flows_to_contract?: boolean;
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
  category?: string | null;
  phase?: string | null;
  procurement_item_id?: number | null;
  flows_to_contract?: boolean;
  reason: string;
}

export interface ExtractionRequest {
  document_id: number;
}

export interface ProcurementItemSpecificationResponse {
  id: number;
  name: string;
  normalized_name?: string | null;
  value: string;
  mandatory: boolean;
  source_page?: number | null;
  confidence?: number | null;
}

export interface ProcurementItemResponse {
  id: number;
  case_id: number;
  item_number?: string | null;
  description: string;
  quantity?: number | null;
  unit?: string | null;
  status: string;
  source_document_id?: number | null;
  source_page?: number | null;
  source_requirement_id?: number | null;
  confidence?: number | null;
  specifications: ProcurementItemSpecificationResponse[];
}
