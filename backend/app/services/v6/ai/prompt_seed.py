from sqlalchemy.orm import Session
from app.models.v6.prompt_registry import PromptRegistry

class PromptSeedService:
    @staticmethod
    def seed_prompts(db: Session):
        prompts = [
            {
                "name": "case_summary",
                "version": "v1",
                "content": "Eres un AI Assistant. Usando el JSON provisto, resume el caso. DECLARA SIEMPRE QUE REQUIERES VALIDACION HUMANA."
            },
            {
                "name": "requirement_explanation",
                "version": "v1",
                "content": "Eres un AI Assistant. Explica los requisitos tecnicos del caso. DECLARA SIEMPRE QUE REQUIERES VALIDACION HUMANA."
            },
            {
                "name": "comparison_summary",
                "version": "v1",
                "content": "Compara las ofertas basandote en las evaluaciones. NO adjudiques a ningun proveedor. DECLARA SIEMPRE QUE REQUIERES VALIDACION HUMANA."
            }
        ]
        
        for p_data in prompts:
            existing = db.query(PromptRegistry).filter_by(name=p_data["name"]).first()
            if not existing:
                new_prompt = PromptRegistry(
                    name=p_data["name"],
                    version=p_data["version"],
                    content=p_data["content"]
                )
                db.add(new_prompt)
        
        db.commit()
