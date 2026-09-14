from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.domain import CaseFile
from app.services.v6.ai.prompt_seed import PromptSeedService

def test_ai_ask_and_history(admin_client: TestClient, db_session: Session, setup_mega_tenant):
    # Seed prompts
    PromptSeedService.seed_prompts(db_session)
    
    case = CaseFile(title="AI Chat Test", contract_type="BIENES", tenant_id="mega_tenant")
    db_session.add(case)
    db_session.commit()
    
    # 1. Ask a question
    payload = {"question": "Cual es el resumen del caso?"}
    response = admin_client.post(f"/api/v6/ai/cases/{case.id}/ask", json=payload)
    
    assert response.status_code == 200, response.text
    data = response.json()
    assert "REQUIERE VALIDACION HUMANA" in data["answer"]
    assert "Context Snapshot" in data["sources"]
    interaction_id = data["interaction_id"]
    
    # 2. Retrieve history log
    hist_res = admin_client.get(f"/api/v6/ai/interactions/{interaction_id}")
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert hist_data["question"] == "Cual es el resumen del caso?"
    assert hist_data["provider"] == "MOCK"
