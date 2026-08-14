import csv
import io
from typing import List, Dict, Any, Generator
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.v6.case_operational_snapshot import CaseOperationalSnapshot
from app.models.domain import AuditLog
from fastapi import HTTPException

class SupervisorExportSchema:
    VERSION = "supervisor_export_v1"
    
    @staticmethod
    def get_headers() -> List[str]:
        return [
            "Expediente ID",
            "Estado Actual",
            "Nivel Riesgo",
            "Proveedor (RUC)",
            "Sunat",
            "RNP",
            "FUP",
            "CIIU",
            "Monto Experiencia",
            "Bloqueos (Razón)",
            "Acciones Pendientes",
            "Fecha Ultima Actividad",
            "Schema Version"
        ]
        
    @staticmethod
    def format_row(snapshot: CaseOperationalSnapshot, mock_supplier_data: Dict[str, Any]) -> List[str]:
        # Flattening JSONB
        reasons = snapshot.risk_reason if snapshot.risk_reason else []
        reasons_str = " | ".join([f"{r.get('type')}: {r.get('source')}" for r in reasons])
        actions = snapshot.pending_actions if snapshot.pending_actions else []
        actions_str = " | ".join(actions)
        
        return [
            str(snapshot.case_id),
            snapshot.current_status,
            snapshot.risk_level,
            mock_supplier_data.get("ruc", "N/A"),
            mock_supplier_data.get("sunat", "N/A"),
            mock_supplier_data.get("rnp", "N/A"),
            mock_supplier_data.get("fup", "N/A"),
            mock_supplier_data.get("ciiu", "N/A"),
            str(mock_supplier_data.get("experience_amount", 0.0)),
            reasons_str,
            actions_str,
            str(snapshot.updated_at),
            SupervisorExportSchema.VERSION
        ]


class SupervisorExportService:
    def __init__(self, db: Session):
        self.db = db

    def _build_query(self, filters: Dict[str, Any]):
        query = self.db.query(CaseOperationalSnapshot)
        
        if filters.get("risk_level"):
            query = query.filter(CaseOperationalSnapshot.risk_level == filters["risk_level"])
            
        if filters.get("status"):
            query = query.filter(CaseOperationalSnapshot.current_status == filters["status"])
            
        # Date filtering logic (6 months max enforcement)
        end_date = datetime.utcnow()
        start_date_str = filters.get("start_date")
        
        if start_date_str:
            start_date = datetime.fromisoformat(start_date_str)
            if (end_date - start_date).days > 180:
                # Time Range Control (Phase 3)
                raise HTTPException(
                    status_code=400, 
                    detail="El rango de exportacion síncrona supera los 6 meses. Requerido Background Export Job (En desarrollo)."
                )
            query = query.filter(CaseOperationalSnapshot.updated_at >= start_date)
        else:
            # Default to last 30 days if no date provided to protect memory
            query = query.filter(CaseOperationalSnapshot.updated_at >= (end_date - timedelta(days=30)))

        return query

    def _audit_export(self, user_id: int, tenant_id: str, filters: Dict[str, Any], count: int):
        audit = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="EXPORT_GENERATED",
            entity_type="CaseOperationalSnapshot",
            entity_id="BULK",
            details=f"Filters: {filters} | Records: {count} | Schema: {SupervisorExportSchema.VERSION}",
            status="PASSED"
        )
        self.db.add(audit)
        self.db.commit()

    def generate_csv_stream(self, user_id: int, tenant_id: str, filters: Dict[str, Any]) -> Generator[str, None, None]:
        """
        Generates CSV rows lazily using a Generator to support StreamingResponse.
        """
        query = self._build_query(filters)
        total_records = query.count()
        
        # 1. Audit immediately
        self._audit_export(user_id, tenant_id, filters, total_records)
        
        # 2. Yield Headers
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(SupervisorExportSchema.get_headers())
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        
        # 3. Yield Rows iteratively (Mocking supplier data for Architecture pattern)
        for snapshot in query.yield_per(100):
            mock_supplier = {
                "ruc": "20555444333",
                "sunat": "PASSED",
                "rnp": "PASSED",
                "fup": "PASSED",
                "ciiu": "WARNING",
                "experience_amount": 150000.0
            }
            row = SupervisorExportSchema.format_row(snapshot, mock_supplier)
            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
