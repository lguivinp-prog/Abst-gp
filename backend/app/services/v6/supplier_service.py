from sqlalchemy.orm import Session
from app.models.v6.supplier import Supplier
from app.models.domain import AuditLog

class SupplierService:
    @staticmethod
    def create_supplier(db: Session, user_id: int, tenant_id: str, data: dict) -> Supplier:
        supplier = Supplier(
            tenant_id=tenant_id,
            ruc=data["ruc"],
            business_name=data["business_name"],
            legal_representative=data.get("legal_representative"),
            dni=data.get("dni"),
            contact_email=data.get("contact_email")
        )
        db.add(supplier)
        db.flush()
        
        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="CREATE_SUPPLIER",
            entity_type="Supplier",
            entity_id=str(supplier.id),
            details=f"Created supplier {supplier.ruc}",
            status="SUCCESS"
        )
        db.add(audit)
        db.commit()
        db.refresh(supplier)
        return supplier

    @staticmethod
    def get_supplier(db: Session, supplier_id: int, tenant_id: str) -> Supplier:
        return db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id).first()
