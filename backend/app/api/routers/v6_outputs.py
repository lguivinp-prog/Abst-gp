from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.auth import get_current_active_user, verify_case_access, require_role
from app.api.exceptions import NotFoundException, ForbiddenException
from app.models.domain import User, CaseFile
from app.services.v6.engines.accuracy_gate import ContractAccuracyGate
from app.services.v6.engines.template_engine import OutputTemplateEngine
from app.models.v6.supplier_selection import SupplierSelectionFinal
from app.models.v6.order_preparation_profile import OrderPreparationProfile
from app.models.v6.output_template import OutputTemplate
from app.models.v6.generated_output import GeneratedOutput
from app.models.domain import AuditLog
import json

router = APIRouter()

@router.post("/cases/{case_id}/prepare-output")
def prepare_output(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    # 1. Gate Check
    gate_result = ContractAccuracyGate.validate_for_generation(db, case_id)
    if gate_result == "ACCURACY_FAILED":
        raise HTTPException(status_code=400, detail="El expediente no supero el Contract Accuracy Gate.")
        
    # 2. Get Selection & Profile (Mocking profile data for Sprint 6 if it doesn't exist)
    selection = db.query(SupplierSelectionFinal).filter_by(case_id=case_id).first()
    if not selection:
        raise HTTPException(status_code=400, detail="No existe seleccion final aprobada.")
        
    profile = db.query(OrderPreparationProfile).filter_by(supplier_selection_final_id=selection.id).first()
    if not profile:
        # Mock creation for the sake of the engine demo
        profile = OrderPreparationProfile(
            supplier_selection_final_id=selection.id,
            supplier_data={"supplier_name": "Tech Corp", "supplier_ruc": "20123456789"},
            contracting_data={"contract_amount": 5000},
            improvements_data={}
        )
        db.add(profile)
        db.flush()
        
    # 3. Get Templates
    template = db.query(OutputTemplate).filter_by(type="CONDICIONES", status="ACTIVE").first()
    if not template:
        # Create a mock template if none exists
        template = OutputTemplate(
            type="CONDICIONES", version="1.0", entity_name="Abast-gp",
            content="El proveedor {{ supplier_name }} con RUC {{ supplier_ruc }} proveera por un monto de {{ contract_amount }}."
        )
        db.add(template)
        db.flush()
        
    # 4. Engine Render
    snapshot = {**profile.supplier_data, **profile.contracting_data, **profile.improvements_data}
    try:
        rendered_content, content_hash = OutputTemplateEngine.render_template(template.content, snapshot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # 5. Save GeneratedOutput
    output = GeneratedOutput(
        case_id=case_id,
        template_id=template.id,
        content_rendered=rendered_content,
        generation_hash=content_hash,
        generated_by=current_user.id,
        template_version=template.version,
        accuracy_gate_result=gate_result,
        source_snapshot=snapshot,
        status="GENERATED"
    )
    db.add(output)
    
    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="PREPARE_OUTPUT",
        entity_type="CaseFile",
        entity_id=str(case_id),
        details=json.dumps({"hash": content_hash}),
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    
    return {"id": output.id, "status": output.status, "hash": output.generation_hash}

@router.get("/cases/{case_id}/outputs")
def list_outputs(
    case_id: int,
    case: CaseFile = Depends(verify_case_access),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    outputs = db.query(GeneratedOutput).filter_by(case_id=case.id).all()
    return [{"id": o.id, "type": o.template.type if o.template else "CONDICIONES", "status": o.status} for o in outputs]

@router.post("/outputs/{output_id}/approve")
def approve_output(
    output_id: int,
    current_user: User = Depends(require_role(["ADMIN", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    output = db.query(GeneratedOutput).filter_by(id=output_id).first()
    if not output:
        raise NotFoundException("Output not found")

    case = db.query(CaseFile).filter(
        CaseFile.id == output.case_id,
        CaseFile.tenant_id == current_user.tenant_id
    ).first()
    if not case:
        raise NotFoundException("Output not found")

    output.status = "APPROVED"
    
    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="APPROVE_OUTPUT",
        entity_type="GeneratedOutput",
        entity_id=str(output.id),
        details=json.dumps({}),
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    return {"id": output.id, "status": output.status}

@router.post("/outputs/{output_id}/export")
def export_output(
    output_id: int,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "SUPERVISOR"])),
    db: Session = Depends(get_db)
):
    output = db.query(GeneratedOutput).filter_by(id=output_id).first()
    if not output:
        raise NotFoundException("Output not found")

    case_query = db.query(CaseFile).filter(
        CaseFile.id == output.case_id,
        CaseFile.tenant_id == current_user.tenant_id
    )
    if current_user.role not in ["ADMIN", "SUPERVISOR"]:
        case_query = case_query.filter(CaseFile.assigned_to_user_id == current_user.id)
    case = case_query.first()
    if not case:
        raise NotFoundException("Output not found")

    if output.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Output must be APPROVED before export")

    output.status = "EXPORTED"
    
    audit = AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="EXPORT_OUTPUT",
        entity_type="GeneratedOutput",
        entity_id=str(output.id),
        details=json.dumps({}),
        status="SUCCESS"
    )
    db.add(audit)
    db.commit()
    return {"id": output.id, "status": output.status, "message": "Exportacion simulada exitosa"}
