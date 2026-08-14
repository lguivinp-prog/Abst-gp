import os
import pytest
import io
import tempfile
import hashlib
from pathlib import Path
from app.storage.local import LocalStorageAdapter
from app.storage.factory import get_storage

@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield LocalStorageAdapter(base_dir=temp_dir)

def test_storage_put_and_get(temp_storage):
    tenant_id = "tenant_1"
    doc_id = "doc_123.pdf"
    content = b"fake pdf content"
    
    # Test PUT
    stream = io.BytesIO(content)
    uri = temp_storage.put(tenant_id, doc_id, stream)
    
    assert temp_storage.exists(uri)
    
    # Test GET
    retrieved_stream = temp_storage.get(uri)
    assert retrieved_stream.read() == content
    retrieved_stream.close()

def test_storage_checksum(temp_storage):
    tenant_id = "tenant_2"
    doc_id = "doc_456.png"
    content = b"image content"
    expected_hash = hashlib.sha256(content).hexdigest()
    
    stream = io.BytesIO(content)
    uri = temp_storage.put(tenant_id, doc_id, stream)
    
    actual_hash = temp_storage.checksum(uri)
    assert actual_hash == expected_hash

def test_storage_checksum_validation_failure(temp_storage):
    tenant_id = "tenant_3"
    doc_id = "doc_789.txt"
    content = b"some text"
    bad_hash = "1234567890abcdef"
    
    stream = io.BytesIO(content)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        temp_storage.put(tenant_id, doc_id, stream, expected_checksum=bad_hash)
        
    # Ensure file was not left behind
    assert not temp_storage.exists(f"{temp_storage.base_dir}/{tenant_id}/{doc_id}")

def test_storage_delete(temp_storage):
    tenant_id = "tenant_1"
    doc_id = "delete_me.txt"
    uri = temp_storage.put(tenant_id, doc_id, io.BytesIO(b"content"))
    
    assert temp_storage.exists(uri)
    assert temp_storage.delete(uri) is True
    assert not temp_storage.exists(uri)
    assert temp_storage.delete(uri) is False

def test_storage_missing_document(temp_storage):
    uri = "non_existent_file.txt"
    assert not temp_storage.exists(uri)
    
    with pytest.raises(FileNotFoundError):
        temp_storage.get(uri)
        
    with pytest.raises(FileNotFoundError):
        temp_storage.checksum(uri)
        
    with pytest.raises(FileNotFoundError):
        temp_storage.metadata(uri)

def test_factory_returns_local_by_default():
    storage = get_storage()
    assert isinstance(storage, LocalStorageAdapter)
