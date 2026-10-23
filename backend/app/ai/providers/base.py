import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class TextDelta:
    text: str
    provider_data: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    call_id: str | None = None
    provider_data: dict[str, Any] | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


LLMEvent = TextDelta | ToolCall | Usage
ToolSpec = dict[str, Any]
ChatMessage = dict[str, Any]


class ProviderUnavailableError(RuntimeError):
    pass


class StructuredOutputError(RuntimeError):
    pass


class LLMProvider(Protocol):
    def stream_chat(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> Iterator[LLMEvent]: ...

    def generate_json(
        self,
        system: str,
        prompt: str,
        schema: type[BaseModel],
        model: Literal["fast", "main"] = "main",
    ) -> BaseModel: ...


class ProviderBase:
    def stream_chat(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> Iterator[LLMEvent]:
        raise NotImplementedError

    def generate_json(
        self,
        system: str,
        prompt: str,
        schema: type[BaseModel],
        model: Literal["fast", "main"] = "main",
    ) -> BaseModel:
        repair_path = Path(__file__).resolve().parents[2] / "prompts" / "json_repair.md"
        repair_template = repair_path.read_text(encoding="utf-8")
        last_error = "A resposta estava vazia."
        current_prompt = prompt
        for attempt in range(3):
            raw = self._generate_json_text(system, current_prompt, schema, model)
            try:
                return schema.model_validate(json.loads(raw))
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
                last_error = str(error)[:400]
                if attempt == 2:
                    break
                repair = repair_template.replace("{{ERROR}}", last_error)
                current_prompt = f"{prompt}\n\n<resposta_anterior>\n{raw[:6000]}\n</resposta_anterior>\n\n{repair}"
        raise StructuredOutputError("A saída estruturada não passou na validação.")

    def _generate_json_text(
        self,
        system: str,
        prompt: str,
        schema: type[BaseModel],
        model: Literal["fast", "main"],
    ) -> str:
        raise NotImplementedError


def is_retryable_error(error: Exception) -> bool:
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    response = getattr(error, "response", None)
    status = status or getattr(response, "status_code", None)
    try:
        return int(status) in {429, 503}
    except (TypeError, ValueError):
        return False


def retry_delay(attempt: int) -> None:
    import time

    time.sleep(0.2 * (attempt + 1))
