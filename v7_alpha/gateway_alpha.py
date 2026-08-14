import psycopg2
import numpy as np
import time
import re
import uuid
import json

# --- CONFIGURATION ---
DB_URL = "postgresql://v7_admin:v7_password@localhost:5433/vector_store"
TENANT_ID = "MINISTERIO-01"

# --- FASE 1: SECURE GATEWAY PIPELINE ---
class PositionBasedMaskingEngine:
    def __init__(self):
        self.patterns = [
            ("RUC", re.compile(r'\b(10|20)\d{9}\b')),
            ("DNI", re.compile(r'\b\d{8}\b'))
        ]
        
    def mask(self, text):
        matches = []
        for label, regex in self.patterns:
            for match in regex.finditer(text):
                matches.append({"start": match.start(), "end": match.end(), "label": label})
        
        matches.sort(key=lambda x: x["start"], reverse=True)
        masked_text = text
        for match in matches:
            tag = f"[{match['label']}_MASKED]"
            masked_text = masked_text[:match["start"]] + tag + masked_text[match["end"]:]
            
        return masked_text

class GatewayPolicyEngine:
    def evaluate_request(self, masked_text):
        if re.search(r'\d{8,}', masked_text):
            return "BLOCK"
        return "ALLOW"
        
    def evaluate_response(self, response_data):
        # AI MUST provide evidence
        if not response_data.get("evidence_references"):
            return "BLOCK_NO_EVIDENCE"
        if response_data.get("confidence_score", 0) < 0.5:
            return "BLOCK_LOW_CONFIDENCE"
        return "ALLOW"

# --- FASE 2: PGVECTOR ALPHA (Vector Store) ---
class VectorStore:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)
        self.setup()
        
    def setup(self):
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS v7_chunks (
                    id SERIAL PRIMARY KEY,
                    chunk_id VARCHAR(50),
                    tenant_id VARCHAR(50),
                    content TEXT,
                    embedding vector(3)
                );
            """)
            self.conn.commit()
            
    def insert(self, chunk_id, tenant_id, content, embedding):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO v7_chunks (chunk_id, tenant_id, content, embedding)
                VALUES (%s, %s, %s, %s)
            """, (chunk_id, tenant_id, content, embedding.tolist()))
            self.conn.commit()
            
    def search(self, tenant_id, query_embedding, limit=2):
        with self.conn.cursor() as cur:
            # L2 distance search (<->) isolating by tenant_id
            cur.execute("""
                SELECT chunk_id, content 
                FROM v7_chunks 
                WHERE tenant_id = %s
                ORDER BY embedding <-> %s::vector 
                LIMIT %s
            """, (tenant_id, query_embedding.tolist(), limit))
            return cur.fetchall()

# --- FASE 3: COGNITIVE MOCK PROVIDER ---
class MockCognitiveEngine:
    def infer(self, request_payload):
        # Simulated Network Delay
        time.sleep(0.5)
        
        # Verify mTLS and JWT conceptually (would be handled by reverse proxy in reality)
        if not request_payload.get("jwt"):
            return {"error": "UNAUTHORIZED"}
            
        context = " ".join([c["text"] for c in request_payload["context_chunks"]])
        
        # Generate fake response based on context
        response_text = f"Basado en los documentos: El proveedor {context.split()[4]} tiene penalidades."
        
        return {
            "request_id": request_payload["request_id"],
            "response": response_text,
            "confidence_score": 0.92,
            "evidence_references": [c["id"] for c in request_payload["context_chunks"]],
            "model_version": "abast-mock-v7"
        }

# --- FASE 5: END TO END ALPHA FLOW ---
def run_e2e_alpha():
    print("--- STARTING V7 ALPHA E2E FLOW ---")
    
    masker = PositionBasedMaskingEngine()
    policy = GatewayPolicyEngine()
    vstore = VectorStore()
    ai_cloud = MockCognitiveEngine()
    
    # 1. Ingestion de Documento
    print("\n1. Ingestion Documento")
    raw_doc = "El proveedor ACME con RUC 20987654321 tiene una penalidad del 10%."
    print(f"   Raw: {raw_doc}")
    
    # 2. Sanitizacion
    print("\n2. Sanitizacion (Gateway)")
    masked_doc = masker.mask(raw_doc)
    dec = policy.evaluate_request(masked_doc)
    print(f"   Masked: {masked_doc}")
    print(f"   Policy Decision: {dec}")
    if dec != "ALLOW": return
    
    # 3. Vectorizacion (Simulada localmente)
    print("\n3. Vector Store Insert (pgvector)")
    fake_embedding = np.array([0.1, 0.2, 0.3])
    chunk_id = "chunk_001"
    vstore.insert(chunk_id, TENANT_ID, masked_doc, fake_embedding)
    print("   Insert successful.")
    
    # 4. RAG Retrieval
    print("\n4. User Query & Retrieval")
    user_query = "Cuales son las penalidades del proveedor 20987654321?"
    masked_query = masker.mask(user_query) # Mask the query too!
    query_embedding = np.array([0.1, 0.2, 0.28]) # Similar vector
    
    results = vstore.search(TENANT_ID, query_embedding)
    print(f"   Masked Query: {masked_query}")
    print(f"   Retrieved Chunks: {len(results)}")
    
    # 5. Cloud Inference
    print("\n5. Cognitive Cloud Request")
    req_id = str(uuid.uuid4())
    payload = {
        "request_id": req_id,
        "tenant_id": TENANT_ID,
        "jwt": "fake.jwt.token", # Fase 4 Security
        "query": masked_query,
        "context_chunks": [{"id": r[0], "text": r[1]} for r in results]
    }
    
    ai_response = ai_cloud.infer(payload)
    print(f"   Cloud Response: {ai_response['response']}")
    
    # 6. Response Governance
    print("\n6. Response Governance")
    final_dec = policy.evaluate_response(ai_response)
    print(f"   Decision: {final_dec}")
    print(f"   Evidence Confirmed: {ai_response['evidence_references']}")
    
    print("\n--- E2E FLOW COMPLETED SUCCESSFULLY ---")

if __name__ == "__main__":
    # Wait for DB to be ready
    for _ in range(5):
        try:
            conn = psycopg2.connect(DB_URL)
            conn.close()
            break
        except:
            time.sleep(1)
            
    run_e2e_alpha()
