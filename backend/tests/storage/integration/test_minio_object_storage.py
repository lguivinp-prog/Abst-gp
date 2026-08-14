import io
import os
import pytest
import hashlib
from app.storage.object import ObjectStorageAdapter
from app.storage.local import LocalStorageAdapter
from app.core.config import settings

# This test requires MinIO to be running and accessible at settings.S3_ENDPOINT_URL
# It will validate real connection and operations, as well as parity with LocalStorageAdapter.

@pytest.fixture(scope="module")
def minio_storage():
    try:
        import boto3
        storage = ObjectStorageAdapter()
        # Ping the service to see if it's up
        storage.s3_client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
        return storage
    except Exception as e:
        pytest.skip(f"MinIO not available or boto3 not installed: {e}")

@pytest.fixture(scope="module")
def local_storage():
    # Use a specific temp dir or the default uploads dir
    return LocalStorageAdapter()

def test_minio_real_connection_and_crud(minio_storage):
    tenant_id = "tenant_minio"
    doc_id = "test_doc_real.txt"
    content = b"Integration test against real MinIO container"
    
    stream = io.BytesIO(content)
    
    # 1. Put
    uri = minio_storage.put(tenant_id, doc_id, stream)
    assert uri == f"{tenant_id}/{doc_id}"
    
    # 2. Exists
    assert minio_storage.exists(uri) is True
    
    # 3. Get
    retrieved = minio_storage.get(uri)
    assert retrieved.read() == content
    
    # 4. Checksum and Metadata
    expected_hash = hashlib.sha256(content).hexdigest()
    assert minio_storage.checksum(uri) == expected_hash
    
    meta = minio_storage.metadata(uri)
    assert meta["size_bytes"] == len(content)
    assert meta["sha256_checksum"] == expected_hash
    
    # 5. Delete
    assert minio_storage.delete(uri) is True
    assert minio_storage.exists(uri) is False

def test_storage_parity_local_vs_object(minio_storage, local_storage):
    tenant_id = "tenant_parity"
    doc_id = "parity_doc.pdf"
    content = b"Parity test payload: checking exact behavior"
    
    # Upload to both
    uri_minio = minio_storage.put(tenant_id, doc_id, io.BytesIO(content))
    uri_local = local_storage.put(tenant_id, doc_id, io.BytesIO(content))
    
    # Compare Get
    data_minio = minio_storage.get(uri_minio).read()
    data_local = local_storage.get(uri_local).read()
    assert data_minio == data_local == content
    
    # Compare Checksum
    hash_minio = minio_storage.checksum(uri_minio)
    hash_local = local_storage.checksum(uri_local)
    assert hash_minio == hash_local
    
    # Compare Exists
    assert minio_storage.exists(uri_minio) == local_storage.exists(uri_local) == True
    
    # Cleanup both
    minio_storage.delete(uri_minio)
    local_storage.delete(uri_local)
    
    assert minio_storage.exists(uri_minio) == local_storage.exists(uri_local) == False
