from .base import DocumentStorage
from .local import LocalStorageAdapter
from .factory import get_storage

__all__ = ["DocumentStorage", "LocalStorageAdapter", "get_storage"]
