import logging
from threading import Lock
from types import SimpleNamespace

import pytest
from google.genai import types
from pydantic import BaseModel

from app.ai.providers.base import ProviderUnavailableError, TextDelta, ToolCall
from app.ai.providers.gemini import GeminiProvider


class ResourceExhaustedError(Exception):
    code = 429
    status = "RESOURCE_EXHAUSTED"


def _provider(client, model_main="gemini-test", fallbacks=()):
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.client = client
    provider.model_main = model_main
    provider.model_fast = "gemini-fast-test"
    provider.model_main_fallbacks = tuple(fallbacks)
    provider._exhausted_models = {}
    provider._quota_lock = Lock()
    return provider


def test_gemini_stream_chat_captures_candidate_part_signatures():
    unsigned_function_part = types.Part.from_function_call(
        name="search_knowledge", args={"query": "apoio"}
    )
    signed_function_part = unsigned_function_part.model_copy(
        update={"thought_signature": b"tool-signature"}
    )
    first_chunk = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="Pensando", thought_signature=b"text-signature"),
                        types.Part(thought_signature=b"signature-only"),
                        unsigned_function_part,
                    ],
                )
            )
        ]
    )
    second_chunk = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        signed_function_part,
                    ],
                )
            )
        ]
    )
    provider = _provider(
        SimpleNamespace(
            models=SimpleNamespace(
                generate_content_stream=lambda **kwargs: iter([first_chunk, second_chunk])
            )
        )
    )

    events = list(provider.stream_chat("system", [], []))

    text_events = [event for event in events if isinstance(event, TextDelta)]
    tool_event = next(event for event in events if isinstance(event, ToolCall))
    assert [event.provider_data for event in text_events] == [
        {"thought_signature": b"text-signature"},
        {"thought_signature": b"signature-only"},
    ]
    assert tool_event.provider_data == {"thought_signature": b"tool-signature"}
    assert tool_event.model == "gemini-test"


def test_gemini_contents_rebuilds_signed_text_and_function_parts():
    provider = GeminiProvider.__new__(GeminiProvider)
    contents = provider._contents(
        [
            {
                "role": "assistant",
                "content": "Pensando",
                "text_parts": [
                    {
                        "text": "Pensando",
                        "provider_data": {"thought_signature": b"text-signature"},
                    },
                    {
                        "text": None,
                        "provider_data": {"thought_signature": b"empty-text-signature"},
                    },
                ],
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "search_knowledge",
                            "arguments": '{"query": "apoio"}',
                        },
                        "provider_data": {"thought_signature": b"tool-signature"},
                    }
                ],
            }
        ]
    )

    parts = contents[0].parts
    assert parts[0].text == "Pensando"
    assert parts[0].thought_signature == b"text-signature"
    assert parts[1].text == ""
    assert parts[1].thought_signature == b"empty-text-signature"
    assert parts[2].function_call.name == "search_knowledge"
    assert parts[2].thought_signature == b"tool-signature"


def test_stream_falls_back_on_resource_exhausted_without_backoff(monkeypatch, caplog):
    models = []
    fallback_call = types.Part.from_function_call(
        name="search_knowledge", args={"query": "apoio"}
    ).model_copy(update={"thought_signature": b"fallback-signature"})
    fallback_chunk = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[fallback_call]))]
    )

    def generate_content_stream(**kwargs):
        models.append(kwargs["model"])
        if kwargs["model"] == "gemini-main-test":
            raise ResourceExhaustedError()
        return iter([fallback_chunk])

    provider = _provider(
        SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate_content_stream)),
        model_main="gemini-main-test",
        fallbacks=("gemini-fallback-test",),
    )
    monkeypatch.setattr(
        "app.ai.providers.gemini.retry_delay",
        lambda attempt: pytest.fail("quota fallback must not back off"),
    )

    with caplog.at_level(logging.INFO, logger="app.ai"):
        events = list(provider.stream_chat("system", [], []))

    call = next(event for event in events if isinstance(event, ToolCall))
    assert models == ["gemini-main-test", "gemini-fallback-test"]
    assert call.provider_data == {"thought_signature": b"fallback-signature"}
    assert call.model == "gemini-fallback-test"
    assert "model_fallback from=gemini-main-test to=gemini-fallback-test" in caplog.text

    list(provider.stream_chat("system", [], []))
    assert models == [
        "gemini-main-test",
        "gemini-fallback-test",
        "gemini-fallback-test",
    ]


def test_stream_does_not_fallback_after_text_was_emitted():
    models = []
    text_chunk = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text="Já respondi")])
            )
        ]
    )

    def generate_content_stream(**kwargs):
        models.append(kwargs["model"])

        def chunks():
            yield text_chunk
            raise ResourceExhaustedError()

        return chunks()

    provider = _provider(
        SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate_content_stream)),
        model_main="gemini-main-test",
        fallbacks=("gemini-fallback-test",),
    )
    events = provider.stream_chat("system", [], [])

    assert next(events) == TextDelta("Já respondi")
    with pytest.raises(ProviderUnavailableError):
        next(events)
    assert models == ["gemini-main-test"]


def test_generate_json_falls_back_on_resource_exhausted():
    class JsonResult(BaseModel):
        answer: str

    models = []

    def generate_content(**kwargs):
        models.append(kwargs["model"])
        if kwargs["model"] == "gemini-main-test":
            raise ResourceExhaustedError()
        result = JsonResult(answer="ok")
        return SimpleNamespace(parsed=result, text=result.model_dump_json())

    provider = _provider(
        SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)),
        model_main="gemini-main-test",
        fallbacks=("gemini-fallback-test",),
    )

    response = provider.generate_json("system", "prompt", JsonResult, model="main")

    assert response.answer == "ok"
    assert models == ["gemini-main-test", "gemini-fallback-test"]
