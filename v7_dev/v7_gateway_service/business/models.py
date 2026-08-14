from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Expediente(Base):
    __tablename__ = "expedientes"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, index=True)
    title = Column(String)
    description = Column(String)
    status = Column(String, default="DRAFT")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner = Column(String)

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True)
    tenant_id = Column(String)
    expediente_id = Column(String, ForeignKey("expedientes.id"))
    filename = Column(String)
    storage_path = Column(String)
    size_bytes = Column(Integer)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Requirement(Base):
    __tablename__ = "requirements"
    id = Column(String, primary_key=True)
    tenant_id = Column(String)
    expediente_id = Column(String, ForeignKey("expedientes.id"))
    value = Column(String)
    category = Column(String)
    source = Column(String)
    page = Column(String)
    evidence = Column(Text)
    status = Column(String) # EXTRACTED, VALIDATED, REJECTED, MANUAL_REQUIRED
    validated_by = Column(String)
    validated_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(String, primary_key=True)
    tenant_id = Column(String)
    expediente_id = Column(String, ForeignKey("expedientes.id"))
    name = Column(String)
    ruc = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Quotation(Base):
    __tablename__ = "quotations"
    id = Column(String, primary_key=True)
    tenant_id = Column(String)
    expediente_id = Column(String, ForeignKey("expedientes.id"))
    supplier_id = Column(String, ForeignKey("suppliers.id"))
    price = Column(Float)
    delivery_days = Column(Integer)
    warranty_months = Column(Integer)
    technical_conditions = Column(Text)
    improvements = Column(Text)
    evidence = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class ExperienceRecord(Base):
    __tablename__ = "experience_records"
    id = Column(String, primary_key=True)
    tenant_id = Column(String)
    expediente_id = Column(String, ForeignKey("expedientes.id"))
    supplier_id = Column(String, ForeignKey("suppliers.id"))
    description = Column(String)
    amount = Column(Float)
    evidence = Column(Text)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class SupervisorDecision(Base):
    __tablename__ = "supervisor_decisions"
    id = Column(String, primary_key=True)
    tenant_id = Column(String)
    expediente_id = Column(String, ForeignKey("expedientes.id"))
    supplier_id = Column(String, ForeignKey("suppliers.id"))
    supervisor_user = Column(String)
    reason = Column(Text)
    evidence_refs = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class GeneratedOutput(Base):
    __tablename__ = "generated_outputs"
    id = Column(String, primary_key=True)
    tenant_id = Column(String)
    expediente_id = Column(String, ForeignKey("expedientes.id"))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String)
    user_id = Column(String)
    entity_id = Column(String)
    action = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
