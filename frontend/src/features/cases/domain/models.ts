/**
 * Modelos de Dominio del Frontend
 *
 * NOTA ARQUITECTÓNICA:
 * Estos modelos representan la "fuente de la verdad" para los componentes UI.
 * Están diseñados para ser agnósticos a la versión del Backend (V1 o V2).
 * 
 * - Los campos garantizados por el backend actual tienen sus tipos base.
 * - Los campos no garantizados o derivados en el frontend se tipan de forma segura (ej. null).
 * - Los campos reservados para el motor V2 se documentan como tales.
 */

export type ReviewStatus = 'pending' | 'reviewed' | 'approved' | 'rejected';
export type MatchStatus = 'match' | 'mismatch' | 'manual_review' | 'not_found';

export interface DocumentSection {
  id: string; // V1 envía integer, V2 enviará UUID. El adapter unifica a string.
  order: number;
  romanNumeral: string | null;
  title: string | null;
  originalText: string;
  currentText: string;
  isSelected: boolean;
  reviewStatus: ReviewStatus;
  
  // Confianza OCR: V1 no entrega un float explícito por sección, el adapter pondrá null
  // V2 entregará confidenceScore.
  confidenceScore: number | null;
  
  // Warnings: V1 entrega JSON crudo, el adapter aplanará a string[].
  warnings: string[];
}

export interface ConditionComparison {
  id: string; // V1 usa un entero de DB, V2 usará UUID. Adapter unifica a string.
  fieldName: string;
  requirementValue: string | null;
  quotationValue: string | null;
  finalValue: string | null;
  status: MatchStatus;
  
  // Confianza de coincidencia: V1 no provee, será null. V2 proveerá este campo.
  confidenceScore: number | null;
  
  // Para futuro visor PDF de doble panel sincrónico
  evidencePage: number | null;
}
