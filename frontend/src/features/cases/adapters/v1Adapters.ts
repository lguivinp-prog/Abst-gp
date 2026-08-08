import type { DocumentSection, ConditionComparison, ReviewStatus, MatchStatus } from '../domain/models';
import type { V1ParsedSectionDto, V1FinalConditionComparisonDto } from './v1Types';

/**
 * Adaptadores puros para transformar DTOs V1 al Modelo de Dominio estable.
 * Son deterministas y seguros (manejan nulls y campos faltantes).
 */

const mapReviewStatus = (status: string | undefined): ReviewStatus => {
  if (!status) return 'pending'; // Estado derivado
  const normalized = status.toLowerCase();
  if (['pending', 'reviewed', 'approved', 'rejected'].includes(normalized)) {
    return normalized as ReviewStatus;
  }
  return 'pending';
};

const mapComparisonStatus = (status: string | undefined): MatchStatus => {
  if (!status) return 'not_found';
  const normalized = status.toLowerCase();
  
  if (normalized.includes('coincide') || normalized === 'pass') return 'match';
  if (normalized.includes('reemplazado') || normalized === 'fail') return 'mismatch';
  if (normalized.includes('manual') || normalized === 'manual_review') return 'manual_review';
  
  return 'manual_review'; // Fallback seguro
};

export const mapV1SectionToDomain = (dto: V1ParsedSectionDto): DocumentSection => {
  // Extraer warnings a un array plano de strings
  let warningsArray: string[] = [];
  if (dto.warnings) {
    warningsArray.push(dto.warnings);
  }
  if (dto.warnings_json && Array.isArray(dto.warnings_json)) {
    dto.warnings_json.forEach(w => {
      if (w.message) warningsArray.push(String(w.message));
      else warningsArray.push(JSON.stringify(w));
    });
  }

  return {
    id: String(dto.id),
    order: dto.original_order ?? 0,
    romanNumeral: dto.original_roman ?? null,
    title: dto.title ?? null,
    originalText: dto.original_text ?? '',
    currentText: dto.current_text ?? '',
    isSelected: Boolean(dto.is_selected),
    reviewStatus: mapReviewStatus(dto.review_status),
    confidenceScore: dto.confidence_score ?? null, // V1 no siempre lo provee
    warnings: warningsArray,
  };
};

export const mapV1ComparisonToDomain = (dto: V1FinalConditionComparisonDto, index: number): ConditionComparison => {
  return {
    id: dto.id ? String(dto.id) : `comp-${index}`,
    fieldName: dto.field_name,
    requirementValue: dto.requirement_value ?? null,
    quotationValue: dto.quotation_value ?? null,
    finalValue: dto.final_value ?? null,
    status: mapComparisonStatus(dto.status),
    confidenceScore: null, // V1 no entrega score en esta tabla
    evidencePage: null, // V1 no rastrea la página
  };
};
