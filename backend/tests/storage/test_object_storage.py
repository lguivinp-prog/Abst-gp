import io
import pytest
import hashlib
from app.storage.object import ObjectStorageAdapter
from botocore.exceptions import ClientError
from app.core.config import settings
import sys

# To avoid requiring MinIO running during basic pytest, we mock the boto3 client
# since the prompt requires us to pass tests cleanly in the DR container without modifying docker-compose DR.

@pytest.fixture
def mock_boto3_client(mocker):
    # If boto3 is not installed, mock sys.modules
    try:
        import boto3
    except ImportError:
        import sys
        from unittest.mock import MagicMock
        sys.modules['boto3'] = MagicMock()
        sys.modules['botocore'] = MagicMock()
        sys.modules['botocore.exceptions'] = MagicMock()
        import boto3

    mock_client = mocker.MagicMock()
    mocker.patch('boto3.client', return_value=mock_client)
    return mock_client

@pytest.fixture
def object_storage(mock_boto3_client):
    return ObjectStorageAdapter()

def test_object_storage_put_and_get(object_storage, mock_boto3_client):
    tenant_id = "tenant_obj"
    doc_id = "doc_obj.pdf"
    content = b"fake s3 content"
    
    stream = io.BytesIO(content)
    uri = object_storage.put(tenant_id, doc_id, stream)
    
    expected_uri = f"{tenant_id}/{doc_id}"
    assert uri == expected_uri
    
    # Verify upload was called
    mock_boto3_client.upload_fileobj.assert_called_once()
    
    # Mock get_object response
    mock_body = io.BytesIO(content)
    mock_boto3_client.get_object.return_value = {'Body': mock_body}
    
    retrieved = object_storage.get(uri)
    assert retrieved.read() == content
    
def test_object_storage_checksum(object_storage, mock_boto3_client):
    tenant_id = "tenant_chk"
    doc_id = "doc_chk.png"
    content = b"image content s3"
    expected_hash = hashlib.sha256(content).hexdigest()
    
    # Put
    stream = io.BytesIO(content)
    object_storage.put(tenant_id, doc_id, stream)
    
    # Verify the hash was injected in metadata
    kwargs = mock_boto3_client.upload_fileobj.call_args.kwargs
    assert kwargs['ExtraArgs']['Metadata']['sha256_checksum'] == expected_hash
    
    # Test checksum retrieval
    mock_boto3_client.head_object.return_value = {
        'Metadata': {'sha256_checksum': expected_hash}
    }
    
    assert object_storage.checksum("tenant_chk/doc_chk.png") == expected_hash

def test_object_storage_delete(object_storage, mock_boto3_client):
    uri = "tenant/doc.pdf"
    
    # Exists returns true
    mock_boto3_client.head_object.return_value = {}
    
    assert object_storage.delete(uri) is True
    mock_boto3_client.delete_object.assert_called_with(Bucket=settings.S3_BUCKET_NAME, Key=uri)

def test_object_storage_missing_document(object_storage, mock_boto3_client):
    from botocore.exceptions import ClientError
    error_response = {'Error': {'Code': '404', 'Message': 'Not Found'}}
    mock_boto3_client.head_object.side_effect = ClientError(error_response, 'HeadObject')
    
    assert not object_storage.exists("missing.pdf")
    
    with pytest.raises(FileNotFoundError):
        object_storage.checksum("missing.pdf")
        
    with pytest.raises(FileNotFoundError):
        object_storage.metadata("missing.pdf")
        
    mock_boto3_client.get_object.side_effect = ClientError(error_response, 'GetObject')
    with pytest.raises(FileNotFoundError):
        object_storage.get("missing.pdf")
