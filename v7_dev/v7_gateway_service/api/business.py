from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import jwt

router = APIRouter(prefix="/api/v1")

SECRET_KEY = "supersecret"
ALGORITHM = "HS256"

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=60)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

router = APIRouter(prefix="/api/v1")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": role}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid credentials")

# --- Mocks for local productization MVP ---
# In a real scenario, this connects to SQLAlchemy repositories
fake_db = {
    "expedientes": {},
    "documents": {},
    "requirements": {},
    "suppliers": {},
    "quotations": {},
    "evaluations": {},
    "decisions": {}
}

@router.post("/auth/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == "supervisor" and form_data.password == "supervisor":
        token = create_access_token({"sub": "supervisor", "role": "SUPERVISOR", "tenant": "tenant-A"})
        return {"access_token": token, "token_type": "bearer", "role": "SUPERVISOR"}
    if form_data.username == "operator" and form_data.password == "operator":
        token = create_access_token({"sub": "operator", "role": "OPERATOR", "tenant": "tenant-A"})
        return {"access_token": token, "token_type": "bearer", "role": "OPERATOR"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

class ExpedienteReq(BaseModel):
    title: str
    description: str

@router.get("/expedientes")
def list_expedientes(current_user: dict = Depends(get_current_user)):
    return list(fake_db["expedientes"].values())

@router.post("/expedientes")
def create_expediente(req: ExpedienteReq, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["OPERATOR", "SUPERVISOR"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    exp_id = f"EXP-{len(fake_db['expedientes']) + 1}"
    exp = {"id": exp_id, "title": req.title, "description": req.description, "status": "DRAFT", "created_at": datetime.now().isoformat()}
    fake_db["expedientes"][exp_id] = exp
    return exp

@router.post("/expedientes/{id}/documents")
def upload_document(id: str, file: UploadFile = File(...)):
    doc_id = f"DOC-{len(fake_db['documents']) + 1}"
    doc = {"id": doc_id, "expediente_id": id, "filename": file.filename, "status": "READY"}
    fake_db["documents"][doc_id] = doc
    # Auto generate mock requirements for testing
    req_id = f"REQ-{len(fake_db['requirements']) + 1}"
    fake_db["requirements"][req_id] = {"id": req_id, "expediente_id": id, "requirement": "Must have 3 years experience", "status": "EXTRACTED"}
    return doc

@router.get("/expedientes/{id}/requirements")
def list_requirements(id: str):
    return [r for r in fake_db["requirements"].values() if r["expediente_id"] == id]

class ReqUpdate(BaseModel):
    status: str
    value: str

@router.put("/requirements/{id}")
def update_requirement(id: str, req: ReqUpdate):
    if id in fake_db["requirements"]:
        fake_db["requirements"][id]["status"] = req.status
        fake_db["requirements"][id]["value"] = req.value
        return fake_db["requirements"][id]
    raise HTTPException(404)

class SupplierReq(BaseModel):
    name: str
    ruc: str

@router.post("/expedientes/{id}/suppliers")
def add_supplier(id: str, req: SupplierReq):
    sup_id = f"SUP-{len(fake_db['suppliers']) + 1}"
    sup = {"id": sup_id, "expediente_id": id, "name": req.name, "ruc": req.ruc}
    fake_db["suppliers"][sup_id] = sup
    return sup

@router.get("/expedientes/{id}/suppliers")
def list_suppliers(id: str):
    return [s for s in fake_db["suppliers"].values() if s["expediente_id"] == id]

class QuotationReq(BaseModel):
    supplier_id: str
    price: float
    delivery_days: int

@router.post("/expedientes/{id}/quotations")
def add_quotation(id: str, req: QuotationReq):
    q_id = f"QUO-{len(fake_db['quotations']) + 1}"
    quo = {"id": q_id, "expediente_id": id, "supplier_id": req.supplier_id, "price": req.price, "delivery_days": req.delivery_days}
    fake_db["quotations"][q_id] = quo
    return quo

class DecisionReq(BaseModel):
    supplier_id: str
    reason: str

@router.post("/expedientes/{id}/decisions")
def make_decision(id: str, req: DecisionReq):
    dec = {"expediente_id": id, "supplier_id": req.supplier_id, "reason": req.reason, "timestamp": datetime.now().isoformat()}
    fake_db["decisions"][id] = dec
    fake_db["expedientes"][id]["status"] = "APPROVED"
    return dec

@router.post("/expedientes/{id}/contract-accuracy")
def contract_accuracy(id: str):
    return {"status": "PASS", "message": "All validated"}

@router.get("/expedientes/{id}/outputs")
def get_output(id: str):
    return {"html": f"<h1>Contract for {id}</h1><p>Approved.</p>"}
