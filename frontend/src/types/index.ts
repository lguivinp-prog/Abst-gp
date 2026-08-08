export type CaseStatus = 
  | 'CREATED'
  | 'PROCESSING_REQUIREMENT'
  | 'REVIEW_SECTIONS'
  | 'WAITING_QUOTATION'
  | 'COMPARING'
  | 'READY_GENERATE'
  | 'COMPLETED'
  | 'ERROR'
  | 'draft';

export interface Case {
  id: number;
  title: string;
  contract_type: string;
  siga_number?: string; // Reservado para futuro (UX requiere, API V4.9 no)
  office_unit?: string; // Reservado para futuro
  status: CaseStatus;
  created_at: string;
  updated_at?: string;
  last_processing_error?: string;
}

export interface CaseCreate {
  title: string;
  contract_type: string;
}

export interface StructureBlock {
  type: string;
  text: string;
  label?: string;
  order?: number;
  level?: number;
  rows?: Record<string, any>[];
}

export interface Section {
  id: number;
  case_id: number;
  original_roman?: string;
  original_order?: number;
  title?: string;
  original_text?: string;
  current_text?: string;
  cleaned_text?: string;
  normalized_text?: string;
  structure_json?: StructureBlock[];
  corrections_json?: any[];
  warnings_json?: any[];
  extraction_metadata?: any;
  confidence_score?: number;
  is_selected: boolean;
  review_status: string;
  warnings?: string;
}

export interface ComparisonResult {
  field_name: string;
  requirement_value?: string;
  quotation_value?: string;
  final_value?: string;
  status: string;
}

export * from './jobs';
export * from './monitoring';

