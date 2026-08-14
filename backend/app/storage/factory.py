from .base import DocumentStorage
from .local import LocalStorageAdapter
from app.core.config import settings

def get_storage() -> DocumentStorage:
    backend = settings.STORAGE_BACKEND.lower()
    
    if backend == "local":
        return LocalStorageAdapter()
    elif backend == "object_storage":
        from .object import ObjectStorageAdapter
        return ObjectStorageAdapter()
    else:
        return LocalStorageAdapter()
