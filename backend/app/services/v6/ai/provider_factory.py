from app.core.config import settings
from app.services.v6.ai.provider_interface import (
    AIProviderInterface,
    MockAIProvider,
    OpenAIProvider,
    AnthropicProvider,
    AIResponseContract
)
from typing import Dict, Any

class NullAIProvider(AIProviderInterface):
    def ask(self, prompt: str, context: Dict[str, Any], question: str) -> AIResponseContract:
        raise ValueError("AI provider is not configured.")
        
    @property
    def provider_name(self) -> str:
        return "NONE"
        
    @property
    def model_version(self) -> str:
        return "none"

class AIProviderFactory:
    @staticmethod
    def get_provider() -> AIProviderInterface:
        provider_mode = settings.AI_PROVIDER.lower()
        
        if provider_mode == "none":
            return NullAIProvider()
            
        if provider_mode == "mock":
            if settings.APP_ENV == "production":
                return NullAIProvider()
            return MockAIProvider()
            
        # Auto-detect
        if provider_mode in ("auto", "openai") and settings.OPENAI_API_KEY:
            # We would return OpenAIProvider here if we implemented it fully
            # For now we will return NullProvider if we don't have the actual openai client
            return OpenAIProvider()
            
        if provider_mode in ("auto", "anthropic") and settings.ANTHROPIC_API_KEY:
            return AnthropicProvider()
            
        return NullAIProvider()
