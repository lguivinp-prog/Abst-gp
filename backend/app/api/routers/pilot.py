from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.domain import CaseFile, UploadedDocument, ParsedSection
from app.models.v6.structured_tables import StructuredTable, StructuredRow, StructuredCell

router = APIRouter()

@router.get("/documents")
def list_documents(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    docs = (
        db.query(UploadedDocument)
        .join(CaseFile, UploadedDocument.case_id == CaseFile.id)
        .filter(CaseFile.tenant_id == current_user.tenant_id)
        .order_by(UploadedDocument.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": d.id,
            "nombre": d.original_filename,
            "estado": d.processing_status,
            "fecha": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]
@router.get("/documents/{id}")
def get_document(id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    doc = (
        db.query(UploadedDocument)
        .join(CaseFile, UploadedDocument.case_id == CaseFile.id)
        .filter(
            UploadedDocument.id == id,
            CaseFile.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")

    sections = db.query(ParsedSection).filter(ParsedSection.document_id == id).all()
    res_sections = []
    for s in sections:
        tables = db.query(StructuredTable).filter(StructuredTable.section_id == s.id).all()
        res_tables = []
        for t in tables:
            rows = db.query(StructuredRow).filter(StructuredRow.table_id == t.id).order_by(StructuredRow.row_index).all()
            res_rows = []
            for r in rows:
                cells = db.query(StructuredCell).filter(StructuredCell.row_id == r.id).order_by(StructuredCell.col_index).all()
                res_rows.append({
                    "id": r.id,
                    "row_index": r.row_index,
                    "is_header": r.is_header,
                    "cells": [{"id": c.id, "col_index": c.col_index, "content": c.content, "col_span": c.col_span, "row_span": c.row_span} for c in cells]
                })
            res_tables.append({
                "id": t.id,
                "status": t.status,
                "rows": res_rows
            })
        res_sections.append({
            "id": s.id,
            "title": s.title,
            "content": s.original_text,
            "tables": res_tables
        })

    return {
        "id": doc.id,
        "nombre": doc.original_filename,
        "secciones": res_sections
    }

class ReviewRequest(BaseModel):
    ok: bool

@router.post("/tables/{id}/review")
def review_table(id: int, req: ReviewRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if str(current_user.role).lower() not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    table = (
        db.query(StructuredTable)
        .join(ParsedSection, StructuredTable.section_id == ParsedSection.id)
        .join(UploadedDocument, ParsedSection.document_id == UploadedDocument.id)
        .join(CaseFile, UploadedDocument.case_id == CaseFile.id)
        .filter(
            StructuredTable.id == id,
            CaseFile.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not table:
        raise HTTPException(status_code=404, detail="Not found")
    table.status = "approved" if req.ok else "rejected"
    db.commit()
    return {"status": table.status}
