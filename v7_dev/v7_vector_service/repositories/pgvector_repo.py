import psycopg2
from psycopg2.extras import execute_values
import os
import numpy as np

# In a real environment, load from env var, defaulting to docker service name
DB_DSN = os.getenv("PGVECTOR_DSN", "postgresql://v7_dev:devpass@pgvector-dev:5432/v7_db")
EMBEDDING_DIM = 3 # For Alpha PoC we use 3-dimensional mock embeddings

class PgVectorRepository:
    def __init__(self):
        # We don't connect in __init__ because we want to connect per request to set RLS context
        pass
        
    def setup_database(self):
        try:
            conn = psycopg2.connect(DB_DSN)
            conn.autocommit = True
            with conn.cursor() as cur:
                # 1. Setup Extension
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # 2. Setup Table
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS v7_chunks (
                        id SERIAL PRIMARY KEY,
                        tenant_id VARCHAR(50) NOT NULL,
                        chunk_id VARCHAR(100) NOT NULL,
                        content TEXT NOT NULL,
                        embedding vector({EMBEDDING_DIM}) NOT NULL,
                        document_hash VARCHAR(64) NOT NULL,
                        embedding_model VARCHAR(50) NOT NULL,
                        embedding_version VARCHAR(20) NOT NULL,
                        source_type VARCHAR(20) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # 3. Setup HNSW Index (Requires pgvector 0.5+)
                # We use a simple index creation, assuming pgvector > 0.5
                try:
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS v7_chunks_embedding_idx 
                        ON v7_chunks USING hnsw (embedding vector_l2_ops);
                    """)
                except Exception as e:
                    print(f"Warning: HNSW index creation failed (maybe pgvector version too low): {e}")

                # 4. Setup Row Level Security (RLS)
                cur.execute("ALTER TABLE v7_chunks ENABLE ROW LEVEL SECURITY;")
                
                # Drop existing policy if exists to recreate it cleanly
                cur.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON v7_chunks;")
                
                # Create policy using session variable
                cur.execute("""
                    CREATE POLICY tenant_isolation_policy ON v7_chunks
                    USING (tenant_id = current_setting('app.current_tenant', true));
                """)
            conn.close()
        except Exception as e:
            print(f"DB Setup Error: {e}")

    def insert_chunk(self, tenant_id: str, chunk_id: str, content: str, embedding: list, 
                     doc_hash: str, model: str, version: str, source: str):
        conn = psycopg2.connect(DB_DSN)
        try:
            with conn.cursor() as cur:
                # Enforce RLS context for write
                cur.execute("SET LOCAL app.current_tenant = %s;", (tenant_id,))
                
                cur.execute("""
                    INSERT INTO v7_chunks (tenant_id, chunk_id, content, embedding, 
                                           document_hash, embedding_model, embedding_version, source_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (tenant_id, chunk_id, content, embedding, doc_hash, model, version, source))
            conn.commit()
        finally:
            conn.close()

    def search_chunks(self, tenant_id: str, query_embedding: list, top_k: int = 5):
        conn = psycopg2.connect(DB_DSN)
        try:
            with conn.cursor() as cur:
                # Enforce RLS context for read!
                cur.execute("SET LOCAL app.current_tenant = %s;", (tenant_id,))
                
                cur.execute("""
                    SELECT chunk_id, content, (embedding <-> %s::vector) as distance
                    FROM v7_chunks
                    ORDER BY embedding <-> %s::vector
                    LIMIT %s;
                """, (query_embedding, query_embedding, top_k))
                
                rows = cur.fetchall()
                return rows
        finally:
            conn.close()

vector_repo = PgVectorRepository()
