from .base import DocumentStorage
from .local import LocalStorageAdapter
from app.core.config import settings

def get_storage() -> DocumentStorage:
    # Always return LocalStorageAdapter as AWS and Object Storage are disabled
    return LocalStorageAdapter()
