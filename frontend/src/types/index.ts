export interface Case {
  id: number;
  title: string;
  contract_type: string;
  siga_number?: string;
  office_unit?: string;
  status: string;
  created_at: string;
  updated_at?: string;
  last_processing_error?: string;
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
