from abc import ABC, abstractmethod
from typing import Dict, Any, List

class AIResponseContract:
    def __init__(self, answer: str, sources: List[str], evidence_references: List[str]):
        self.answer = answer
        self.sources = sources
        self.evidence_references = evidence_references

class AIProviderInterface(ABC):
    @abstractmethod
    def ask(self, prompt: str, context: Dict[str, Any], question: str) -> AIResponseContract:
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass
        
    @property
    @abstractmethod
    def model_version(self) -> str:
        pass

class MockAIProvider(AIProviderInterface):
    def ask(self, prompt: str, context: Dict[str, Any], question: str) -> AIResponseContract:
        # Strict mock enforcing AIResponseContract
        answer = f"Mocked AI response to: {question}\n*REQUIERE VALIDACION HUMANA*"
        sources = ["Context Snapshot"]
        evidence_references = []
        if "evaluations" in context:
            evidence_references.append("Case Evaluations")
            
        return AIResponseContract(answer=answer, sources=sources, evidence_references=evidence_references)
        
    @property
    def provider_name(self) -> str:
        return "MOCK"
        
    @property
    def model_version(self) -> str:
        return "mock-1.0"

# Future Adapters
class OpenAIProvider(AIProviderInterface):
    def ask(self, prompt: str, context: Dict[str, Any], question: str) -> AIResponseContract:
        raise NotImplementedError("OpenAI connection not yet implemented")
    @property
    def provider_name(self) -> str: return "OPENAI"
    @property
    def model_version(self) -> str: return "gpt-4"

class AnthropicProvider(AIProviderInterface):
    def ask(self, prompt: str, context: Dict[str, Any], question: str) -> AIResponseContract:
        raise NotImplementedError("Anthropic connection not yet implemented")
    @property
    def provider_name(self) -> str: return "ANTHROPIC"
    @property
    def model_version(self) -> str: return "claude-3-opus"

class LocalLLMProvider(AIProviderInterface):
    def ask(self, prompt: str, context: Dict[str, Any], question: str) -> AIResponseContract:
        raise NotImplementedError("Local LLM connection not yet implemented")
    @property
    def provider_name(self) -> str: return "LOCAL"
    @property
    def model_version(self) -> str: return "llama-3"
