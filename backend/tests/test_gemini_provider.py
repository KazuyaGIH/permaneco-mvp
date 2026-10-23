from types import SimpleNamespace

from google.genai import types

from app.ai.providers.base import TextDelta, ToolCall
from app.ai.providers.gemini import GeminiProvider


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
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content_stream=lambda **kwargs: iter([first_chunk, second_chunk])
        )
    )
    provider.model_main = "gemini-test"

    events = list(provider.stream_chat("system", [], []))

    text_events = [event for event in events if isinstance(event, TextDelta)]
    tool_event = next(event for event in events if isinstance(event, ToolCall))
    assert [event.provider_data for event in text_events] == [
        {"thought_signature": b"text-signature"},
        {"thought_signature": b"signature-only"},
    ]
    assert tool_event.provider_data == {"thought_signature": b"tool-signature"}


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
