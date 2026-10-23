from functools import lru_cache

from app.ai.providers.base import ProviderUnavailableError
from app.ai.providers.fake import FakeLLMProvider
from app.core.config import settings


@lru_cache(maxsize=1)
def get_provider():
    if settings.llm_provider == "fake":
        return FakeLLMProvider()
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise ProviderUnavailableError("O provedor de IA está indisponível.")
        from app.ai.providers.gemini import GeminiProvider

        return GeminiProvider(
            settings.gemini_api_key,
            settings.llm_model_main,
            settings.llm_model_fast,
            settings.llm_timeout_seconds,
        )
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise ProviderUnavailableError("O provedor de IA está indisponível.")
        from app.ai.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            settings.openai_api_key,
            settings.llm_model_main,
            settings.llm_model_fast,
            settings.llm_timeout_seconds,
        )
    raise ProviderUnavailableError("O provedor de IA está indisponível.")
