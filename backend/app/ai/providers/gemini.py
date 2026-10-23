import json
from collections import OrderedDict
from typing import Any, Literal

from google import genai
from google.genai import types
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


class GeminiProvider(ProviderBase):
    def __init__(
        self,
        api_key: str,
        model_main: str,
        model_fast: str,
        timeout_seconds: int = 30,
    ):
        retry_options = types.HttpRetryOptions(attempts=1, http_status_codes=[])
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout_seconds * 1000, retry_options=retry_options
            ),
        )
        self.model_main = model_main
        self.model_fast = model_fast

    def _model(self, model: Literal["fast", "main"]) -> str:
        return self.model_fast if model == "fast" else self.model_main

    def _contents(self, messages: list[ChatMessage]) -> list[types.Content]:
        contents: list[types.Content] = []
        for message in messages:
            role = message.get("role", "user")
            if role == "tool":
                result = message.get("content", "")
                try:
                    response = json.loads(result) if isinstance(result, str) else result
                except json.JSONDecodeError:
                    response = {"result": result}
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=str(message.get("name", "tool")), response=response
                            )
                        ],
                    )
                )
                continue

            parts: list[types.Part] = []
            text_parts = message.get("text_parts")
            if isinstance(text_parts, list) and text_parts:
                for text_part in text_parts:
                    if not isinstance(text_part, dict):
                        continue
                    text = text_part.get("text", "")
                    if text is None:
                        text = ""
                    provider_data = text_part.get("provider_data")
                    signature = (
                        provider_data.get("thought_signature")
                        if isinstance(provider_data, dict)
                        else None
                    )
                    if isinstance(text, str) and (text or signature is not None):
                        parts.append(types.Part(text=text, thought_signature=signature))
            else:
                text = message.get("content")
                if isinstance(text, str) and text:
                    provider_data = message.get("provider_data")
                    signature = (
                        provider_data.get("thought_signature")
                        if isinstance(provider_data, dict)
                        else None
                    )
                    text_part = types.Part.from_text(text=text)
                    if signature is not None:
                        text_part = text_part.model_copy(update={"thought_signature": signature})
                    parts.append(text_part)
            for call in message.get("tool_calls", []):
                function = call.get("function", call)
                arguments = function.get("arguments", function.get("args", {}))
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                part = types.Part.from_function_call(
                    name=str(function.get("name", "")), args=arguments
                )
                provider_data = call.get("provider_data")
                signature = (
                    provider_data.get("thought_signature")
                    if isinstance(provider_data, dict)
                    else None
                )
                if signature is not None:
                    part = part.model_copy(update={"thought_signature": signature})
                parts.append(part)
            if parts:
                contents.append(
                    types.Content(role="model" if role == "assistant" else "user", parts=parts)
                )
        return contents

    @staticmethod
    def _candidate_parts(chunk: types.GenerateContentResponse) -> list[types.Part]:
        candidates = chunk.candidates or []
        if not candidates or candidates[0].content is None:
            return []
        return candidates[0].content.parts or []

    def _tools(self, tools: list[ToolSpec]) -> list[types.Tool]:
        if not tools:
            return []
        declarations = [
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters_json_schema=tool["parameters"],
            )
            for tool in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    def stream_chat(self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]):
        emitted = False
        for attempt in range(3):
            calls: OrderedDict[str, dict[str, Any]] = OrderedDict()
            call_names: dict[str, str] = {}
            call_ids: dict[str, str | None] = {}
            call_signatures_by_id: dict[str, bytes] = {}
            call_signatures_by_name: dict[str, bytes] = {}
            usage: Usage | None = None
            try:
                stream = self.client.models.generate_content_stream(
                    model=self.model_main,
                    contents=self._contents(messages),
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        tools=self._tools(tools),
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        ),
                    ),
                )
                for chunk in stream:
                    parts = self._candidate_parts(chunk)
                    text_parts = [
                        part
                        for part in parts
                        if part.text is not None
                        or (part.thought_signature is not None and part.function_call is None)
                    ]
                    if text_parts:
                        for part in text_parts:
                            text = part.text or ""
                            provider_data = (
                                {"thought_signature": part.thought_signature}
                                if part.thought_signature is not None
                                else None
                            )
                            if text or provider_data:
                                emitted = True
                                yield TextDelta(text, provider_data=provider_data)
                    elif not parts and chunk.text:
                        emitted = True
                        yield TextDelta(chunk.text)

                    for part in parts:
                        function_call = part.function_call
                        if function_call is None or part.thought_signature is None:
                            continue
                        if function_call.id:
                            call_signatures_by_id[function_call.id] = part.thought_signature
                        if function_call.name:
                            call_signatures_by_name[function_call.name] = part.thought_signature
                    for call in chunk.function_calls or []:
                        if not call.name:
                            continue
                        key = call.id or call.name
                        args = call.args or call.partial_args or {}
                        calls.setdefault(key, {}).update(args)
                        call_names[key] = call.name
                        call_ids[key] = call.id
                    if chunk.usage_metadata:
                        usage = Usage(
                            input_tokens=chunk.usage_metadata.prompt_token_count or 0,
                            output_tokens=chunk.usage_metadata.candidates_token_count or 0,
                        )
                for key, args in calls.items():
                    emitted = True
                    signature = call_signatures_by_id.get(call_ids.get(key) or "")
                    if signature is None:
                        signature = call_signatures_by_name.get(call_names[key])
                    yield ToolCall(
                        name=call_names[key],
                        args=args,
                        call_id=call_ids.get(key),
                        provider_data=(
                            {"thought_signature": signature} if signature is not None else None
                        ),
                    )
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
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self._model(model),
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_schema=schema,
                    ),
                )
                parsed = response.parsed
                if isinstance(parsed, BaseModel):
                    return parsed.model_dump_json()
                return response.text or ""
            except Exception as error:
                if is_retryable_error(error) and attempt < 2:
                    retry_delay(attempt)
                    continue
                raise ProviderUnavailableError("O provedor de IA está indisponível.") from error
        raise ProviderUnavailableError("O provedor de IA está indisponível.")
