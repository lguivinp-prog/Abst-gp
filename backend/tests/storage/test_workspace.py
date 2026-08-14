import os
import io
import pytest
from app.storage.workspace import materialize_document
from app.storage.factory import get_storage

def test_workspace_materialize_and_cleanup():
    storage = get_storage()
    
    # 1. Prepare dummy data
    tenant_id = "tenant_ws"
    doc_id = "doc_ws.pdf"
    content = b"fake pdf for workspace"
    stream = io.BytesIO(content)
    
    uri = storage.put(tenant_id, doc_id, stream)
    
    temp_path_captured = None
    
    # 2. Test Materialization
    with materialize_document(uri) as local_temp_path:
        temp_path_captured = local_temp_path
        assert os.path.exists(local_temp_path)
        
        with open(local_temp_path, "rb") as f:
            assert f.read() == content
            
    # 3. Test Cleanup (should be deleted after context exits)
    assert not os.path.exists(temp_path_captured)
    
    # 4. Clean up storage
    storage.delete(uri)

def test_workspace_missing_document():
    with pytest.raises(FileNotFoundError, match="Document not found"):
        with materialize_document("non_existent_uri.pdf"):
            pass
