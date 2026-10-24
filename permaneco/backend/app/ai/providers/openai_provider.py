import json
from collections import OrderedDict
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from app.ai.providers.base import (
    ChatMessage,
    ProviderBase,
    ProviderUnavailableError,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
    is_retryable_error,
    retry_delay,
)


class OpenAIProvider(ProviderBase):
    def __init__(
        self,
        api_key: str,
        model_main: str,
        model_fast: str,
        timeout_seconds: int = 30,
    ):
        self.client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        self.model_main = model_main
        self.model_fast = model_fast

    def _model(self, model: Literal["fast", "main"]) -> str:
        return self.model_fast if model == "fast" else self.model_main

    def _messages(self, system: str, messages: list[ChatMessage]) -> list[dict]:
        cleaned_messages = []
        for message in messages:
            cleaned = {
                key: value
                for key, value in message.items()
                if key not in {"provider_data", "text_parts"}
            }
            if isinstance(cleaned.get("tool_calls"), list):
                cleaned["tool_calls"] = [
                    {key: value for key, value in call.items() if key != "provider_data"}
                    for call in cleaned["tool_calls"]
                ]
            cleaned_messages.append(cleaned)
        return [{"role": "system", "content": system}, *cleaned_messages]

    def _tools(self, tools: list[ToolSpec]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                    "strict": True,
                },
            }
            for tool in tools
        ]

    def stream_chat(
        self,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        model: str | None = None,
    ):
        emitted = False
        for attempt in range(3):
            tool_calls: OrderedDict[int, dict] = OrderedDict()
            usage = None
            try:
                stream = self.client.chat.completions.create(
                    model=self.model_main,
                    messages=self._messages(system, messages),
                    tools=self._tools(tools) or None,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                for chunk in stream:
                    if chunk.usage:
                        usage = Usage(
                            input_tokens=chunk.usage.prompt_tokens,
                            output_tokens=chunk.usage.completion_tokens,
                        )
                    for choice in chunk.choices:
                        delta = choice.delta
                        if delta.content:
                            emitted = True
                            yield TextDelta(delta.content)
                        for call in delta.tool_calls or []:
                            item = tool_calls.setdefault(
                                call.index,
                                {"id": call.id, "name": "", "arguments": ""},
                            )
                            if call.id:
                                item["id"] = call.id
                            if call.function and call.function.name:
                                item["name"] += call.function.name
                            if call.function and call.function.arguments:
                                item["arguments"] += call.function.arguments
                for item in tool_calls.values():
                    emitted = True
                    try:
                        args = json.loads(item["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    yield ToolCall(name=item["name"], args=args, call_id=item["id"])
                if usage:
                    yield usage
                return
            except Exception as error:
                if is_retryable_error(error) and attempt < 2 and not emitted:
                    retry_delay(attempt)
                    continue
                raise ProviderUnavailableError("O provedor de IA está indisponível.") from error

    def _generate_json_text(
        self,
        system: str,
        prompt: str,
        schema: type[BaseModel],
        model: Literal["fast", "main"],
    ) -> str:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__.lower(),
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        }
        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self._model(model),
                    messages=self._messages(system, [{"role": "user", "content": prompt}]),
                    response_format=response_format,
                )
                return response.choices[0].message.content or ""
            except Exception as error:
                if is_retryable_error(error) and attempt < 2:
                    retry_delay(attempt)
                    continue
                raise ProviderUnavailableError("O provedor de IA está indisponível.") from error
        raise ProviderUnavailableError("O provedor de IA está indisponível.")
