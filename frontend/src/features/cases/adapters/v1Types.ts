/**
 * Tipos DTO (Data Transfer Objects) que representan exactamente 
 * el contrato actual del Backend V4.9 (V1).
 * 
 * Los componentes React NUNCA deben importar o usar estos tipos directamente.
 */

export interface V1ParsedSectionDto {
  id: number;
  case_id: number;
  original_roman?: string;
  original_order?: number;
  title?: string;
  original_text?: string;
  current_text?: string;
  cleaned_text?: string;
  normalized_text?: string;
  structure_json?: Record<string, any>[];
  corrections_json?: Record<string, any>[];
  warnings_json?: Record<string, any>[];
  extraction_metadata?: Record<string, any>;
  confidence_score?: number; // En V1 a veces viene, usualmente no de forma consistente
  is_selected: boolean;
  review_status: string; // 'pending', 'reviewed', 'approved'
  warnings?: string;
}

export interface V1FinalConditionComparisonDto {
  id: number;
  case_id: number;
  field_name: string;
  requirement_value: string | null;
  quotation_value: string | null;
  final_value: string | null;
  status: string;
}
