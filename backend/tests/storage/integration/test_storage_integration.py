import io
import pytest
from fastapi import UploadFile
from app.storage.factory import get_storage
from app.storage.local import LocalStorageAdapter

# We will test the integration of the storage layer with typical FastAPI/App structures
# mimicking the flow in cases.py

def test_integration_upload_document():
    storage = get_storage()
    # Mocking FastAPI UploadFile
    file_content = b"fake pdf data for integration"
    file_like = io.BytesIO(file_content)
    
    tenant_id = "tenant_int_1"
    doc_id = "doc_int_1.pdf"
    
    saved_path = storage.put(tenant_id, doc_id, file_like)
    
    assert storage.exists(saved_path)
    
    # Descarga
    downloaded_stream = storage.get(saved_path)
    assert downloaded_stream.read() == file_content
    downloaded_stream.close()
    
    # Checksum
    import hashlib
    expected_hash = hashlib.sha256(file_content).hexdigest()
    assert storage.checksum(saved_path) == expected_hash
    
    # Cleanup
    storage.delete(saved_path)

def test_integration_documento_inexistente():
    storage = get_storage()
    
    with pytest.raises(FileNotFoundError):
        storage.get("invalid/path/that/does/not/exist.pdf")
        
    assert storage.exists("invalid/path/that/does/not/exist.pdf") is False

def test_integration_error_storage():
    storage = get_storage()
    # Force a checksum error
    file_content = b"bad data"
    file_like = io.BytesIO(file_content)
    
    with pytest.raises(ValueError, match="Checksum mismatch"):
        storage.put("tenant_err", "doc_err.pdf", file_like, expected_checksum="12345")
