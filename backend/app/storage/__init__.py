from .base import DocumentStorage
from .local import LocalStorageAdapter
from .object import ObjectStorageAdapter
from .factory import get_storage

__all__ = ["DocumentStorage", "LocalStorageAdapter", "ObjectStorageAdapter", "get_storage"]
