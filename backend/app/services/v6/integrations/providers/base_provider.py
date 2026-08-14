from abc import ABC, abstractmethod
from typing import Dict, Any
from datetime import datetime
import hashlib
import json

class ValidationResult:
    def __init__(self, status: str, source: str, payload: Dict[str, Any], schema_version: str = "1.0"):
        self.status = status # PASSED, WARNING, BLOCKED, ERROR, MANUAL_REQUIRED
        self.source = source
        self.payload = payload
        self.schema_version = schema_version
        self.timestamp = datetime.utcnow()
        self.hash = self._generate_hash()
        
    def _generate_hash(self) -> str:
        data_str = json.dumps(self.payload, sort_keys=True)
        return hashlib.sha256(data_str.encode('utf-8')).hexdigest()

class ExternalProviderInterface(ABC):
    @abstractmethod
    def validate(self, identifier: str, fallback_evidence: Dict[str, Any] = None) -> ValidationResult:
        """
        Executes the validation against the provider.
        If API fails or is not configured, it can inspect fallback_evidence.
        If no fallback_evidence is provided and API fails, it returns MANUAL_REQUIRED or WARNING/ERROR.
        """
        pass
