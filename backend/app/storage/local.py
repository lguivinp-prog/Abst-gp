import os
import hashlib
from typing import BinaryIO, Dict, Any, Optional
from pathlib import Path

from .base import DocumentStorage
from app.core.config import settings

class LocalStorageAdapter(DocumentStorage):
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.UPLOADS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_path(self, uri: str) -> Path:
        p = Path(uri)
        if not p.is_absolute():
            p = self.base_dir / p
        return p

    def put(self, tenant_id: str, document_id: str, file_stream: BinaryIO, expected_checksum: Optional[str] = None) -> str:
        tenant_dir = self.base_dir / str(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = tenant_dir / str(document_id)
        
        hasher = hashlib.sha256()
        
        # Ensure we are reading from the start if it's a seekable stream
        if hasattr(file_stream, 'seek') and hasattr(file_stream, 'tell'):
            try:
                if file_stream.tell() != 0:
                    file_stream.seek(0)
            except Exception:
                pass

        with open(file_path, "wb") as f:
            while chunk := file_stream.read(8192):
                hasher.update(chunk)
                f.write(chunk)
                
        actual_checksum = hasher.hexdigest()
        
        if expected_checksum and actual_checksum != expected_checksum:
            os.remove(file_path)
            raise ValueError(f"Checksum mismatch. Expected {expected_checksum}, got {actual_checksum}")
            
        return str(file_path)

    def get(self, uri: str) -> BinaryIO:
        path = self._get_path(uri)
        if not path.exists():
            raise FileNotFoundError(f"Document not found at {uri}")
        return open(path, "rb")

    def delete(self, uri: str) -> bool:
        path = self._get_path(uri)
        if path.exists():
            os.remove(path)
            return True
        return False

    def exists(self, uri: str) -> bool:
        return self._get_path(uri).exists()

    def checksum(self, uri: str) -> str:
        path = self._get_path(uri)
        if not path.exists():
            raise FileNotFoundError(f"Document not found at {uri}")
            
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def metadata(self, uri: str) -> Dict[str, Any]:
        path = self._get_path(uri)
        if not path.exists():
            raise FileNotFoundError(f"Document not found at {uri}")
        stat = path.stat()
        return {
            "size_bytes": stat.st_size,
            "created_at": stat.st_ctime,
            "modified_at": stat.st_mtime,
            "content_type": "application/octet-stream"
        }

    def generate_presigned_url(self, uri: str, expiration: int = 3600) -> str:
        # For local, we just return a fake URL since the backend handles it locally.
        # This allows V2 architecture to mock presigned URLs locally.
        return f"http://localhost/local-storage-mock/upload/{uri}?expires={expiration}"
