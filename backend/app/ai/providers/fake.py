from collections import deque
from collections.abc import Iterable
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel

from app.ai.providers.base import (
    ChatMessage,
    LLMEvent,
    ProviderBase,
    ProviderUnavailableError,
    TextDelta,
    ToolSpec,
)


class FakeLLMProvider(ProviderBase):
    def __init__(
        self,
        stream_responses: Iterable[str | list[LLMEvent]] = (),
        json_responses: Iterable[str] = (),
        down: bool = False,
    ):
        self.stream_responses = deque(stream_responses)
        self.json_responses = deque(json_responses)
        self.down = down
        self.stream_calls: list[list[ChatMessage]] = []

    def stream_chat(self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]):
        del system, tools
        self.stream_calls.append(deepcopy(messages))
        if self.down:
            raise ProviderUnavailableError("O provedor de IA está indisponível.")
        response = (
            self.stream_responses.popleft() if self.stream_responses else "Olá! Como posso ajudar?"
        )
        events = [TextDelta(response)] if isinstance(response, str) else response
        yield from events

    def _generate_json_text(
        self,
        system: str,
        prompt: str,
        schema: type[BaseModel],
        model: Literal["fast", "main"],
    ) -> str:
        del system, prompt, schema, model
        if self.down:
            raise ProviderUnavailableError("O provedor de IA está indisponível.")
        return self.json_responses.popleft() if self.json_responses else "{}"
