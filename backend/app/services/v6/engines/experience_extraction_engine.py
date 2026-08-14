from sqlalchemy.orm import Session
from app.models.v6.experience_evidence import ExperienceEvidence
from typing import List

class ExperienceExtractionEngine:
    def extract_candidates(self, db: Session, offer_id: int, tenant_id: str, case_id: int) -> List[ExperienceEvidence]:
        """
        Uses Restricted RAG to find contract evidence within Anexo 3 or Contrato docs for this specific supplier offer.
        Creates ExperienceEvidence rows with status EXTRACTED.
        """
        # In real implementation:
        # 1. Calls EvidenceRetrievalService with filter {"offer_id": offer_id, "source_type": ["ANEXO_3", "CONTRATO"]}
        # 2. Passes chunks to AssistantService for information extraction (amount, date, object, entity).
        
        # MOCK IMPLEMENTATION FOR ARCHITECTURE
        extracted_mock = ExperienceEvidence(
            supplier_offer_id=offer_id,
            document_type="ANEXO_3",
            evidence_status="EXTRACTED",
            entidad_contratante="Ministerio MOCK",
            objeto="Servicio de Limpieza",
            monto=150000.0,
            raw_fragment="El contratista brindó el servicio por 150000 soles...",
            confidence=0.85
        )
        
        db.add(extracted_mock)
        db.commit()
        db.refresh(extracted_mock)
        return [extracted_mock]
