from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple

class ProviderResult:
    def __init__(self, result: str, status: str, source: str, timestamp: str, payload: Dict[str, Any], hash_val: str):
        self.result = result
        self.status = status # PASSED, WARNING, BLOCKED, ERROR
        self.source = source
        self.timestamp = timestamp
        self.payload = payload
        self.hash = hash_val

class ValidationProviderInterface(ABC):
    @abstractmethod
    def validate(self, identifier: str) -> ProviderResult:
        pass

class SUNATProviderInterface(ValidationProviderInterface):
    pass

class RNPProviderInterface(ValidationProviderInterface):
    pass

class FUPProviderInterface(ValidationProviderInterface):
    pass

class CIIUProviderInterface(ValidationProviderInterface):
    pass
