import { useState, useEffect, useCallback } from 'react';
import type { Case, Section } from '../../../types';
import { casesService } from '../../../api/cases.service';
import { AppError } from '../../../api/apiError';

export function useCaseDetails(caseId: string | undefined) {
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetails = useCallback(async () => {
    if (!caseId) return;
    
    setLoading(true);
    setError(null);
    try {
      const caseRes = await casesService.getCase(caseId);
      setCaseData(caseRes);
      
      try {
        const sectionsRes = await casesService.getSections(caseId);
        setSections(sectionsRes.map(ds => ({
          id: Number(ds.id) || 0,
          case_id: Number(caseId) || 0,
          original_roman: ds.romanNumeral || undefined,
          original_order: ds.order,
          title: ds.title || undefined,
          original_text: ds.originalText,
          current_text: ds.currentText,
          is_selected: ds.isSelected,
          review_status: ds.reviewStatus
        })));
      } catch (err) {
        // Ignorar si no hay secciones aún
        setSections([]);
      }

    } catch (err) {
      if (err instanceof AppError) {
        setError(err.message);
      } else {
        setError('Ocurrió un error inesperado al cargar el expediente.');
      }
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    fetchDetails();
  }, [fetchDetails]);

  return {
    caseData,
    setCaseData,
    sections,
    setSections,
    loading,
    error,
    refresh: fetchDetails
  };
}
