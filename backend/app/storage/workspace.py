import tempfile
import os
from contextlib import contextmanager
from app.storage.factory import get_storage

@contextmanager
def materialize_document(uri: str, suffix: str = ".pdf"):
    """
    Creates a temporary workspace for a document stored in DocumentStorage.
    Downloads the document stream to a local temp file, yields the physical path,
    and guarantees cleanup upon exit.
    """
    storage = get_storage()
    if not storage.exists(uri):
        raise FileNotFoundError(f"Document not found in storage: {uri}")
        
    temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(temp_fd, 'wb') as temp_file:
            stream = storage.get(uri)
            try:
                while chunk := stream.read(8192):
                    temp_file.write(chunk)
            finally:
                if hasattr(stream, 'close'):
                    stream.close()
                
        yield temp_path
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
