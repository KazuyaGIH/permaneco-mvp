import json
import re
from collections.abc import Callable, Iterator
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.context import CANARY, build_context
from app.ai.providers.base import (
    LLMProvider,
    TextDelta,
    ToolCall,
    Usage,
)
from app.ai.tools import execute_tool, tool_specs
from app.core.clock import Clock
from app.core.config import settings
from app.models import (
    Conversation,
    Message,
    SecurityEvent,
    StudentProfile,
    TokenUsage,
)
from app.security.sanitize import detect_prompt_injection, sanitize_message

FRIENDLY_PROVIDER_ERROR = (
    "Desculpe, não consegui responder agora. Sua mensagem foi salva; tente novamente em instantes."
)
FRIENDLY_TOKEN_LIMIT = "Você atingiu o limite diário de uso da mentora. Vamos retomar amanhã."
CANARY_RESPONSE = (
    "Não consigo responder a isso agora. Vamos continuar com o que é importante para você?"
)
_HTML_TAG = re.compile(r"<[^>]*>")
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\((?:<)?([^)\s>]+)(?:>)?(?:\s+['\"][^)]*['\"])?\)")
_BARE_LINK = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>()]+")
MAX_OUTPUT_CHARS = 4000


def _safe_prefix_length(value: str) -> int:
    holdback = len(CANARY) - 1
    boundary = len(value) - holdback
    if boundary <= 0:
        return 0
    boundary = max(value.rfind(" ", 0, boundary), value.rfind("\n", 0, boundary)) + 1
    if boundary <= 0:
        return 0
    if value.rfind("<", 0, boundary) > value.rfind(">", 0, boundary):
        boundary = value.rfind("<", 0, boundary)
    if value.rfind("[", 0, boundary) > value.rfind("]", 0, boundary):
        boundary = value.rfind("[", 0, boundary)
    return max(boundary, 0)


def _record_security_event(db: Session, student_id, event_type: str) -> None:
    db.add(
        SecurityEvent(
            actor_id=student_id,
            event_type=event_type,
            metadata_json={},
        )
    )


def _allowed_url(value: str) -> bool:
    url = value if "://" in value else f"https://{value}"
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(
        host == domain or host.endswith(f".{domain}") for domain in settings.allowed_link_domains
    )


def sanitize_model_output(value: str) -> str:
    value = _MARKDOWN_IMAGE.sub("", value)
    value = _HTML_TAG.sub("", value)

    def markdown_link(match: re.Match) -> str:
        label, link = match.groups()
        return match.group(0) if _allowed_url(link) else label

    value = _MARKDOWN_LINK.sub(markdown_link, value)

    def bare_link(match: re.Match) -> str:
        link = match.group(0).rstrip(".,;:!?")
        suffix = match.group(0)[len(link) :]
        return match.group(0) if _allowed_url(link) else suffix

    value = _BARE_LINK.sub(bare_link, value)
    return value[:MAX_OUTPUT_CHARS]


def _persist_assistant(db: Session, conversation_id, text: str) -> None:
    db.add(
        Message(
            conversation_id=conversation_id,
            role="assistant",
            content=text,
            redaction_flags={},
        )
    )


def _daily_usage(db: Session, student_id, day) -> TokenUsage | None:
    return db.scalar(
        select(TokenUsage).where(TokenUsage.student_id == student_id, TokenUsage.day == day)
    )


def _add_usage(db: Session, student_id, day, tokens: int) -> None:
    if tokens <= 0:
        return
    usage = _daily_usage(db, student_id, day)
    if usage is None:
        db.add(TokenUsage(student_id=student_id, day=day, tokens=tokens))
    else:
        usage.tokens += tokens


def _safe_tool_result(
    call: ToolCall,
    db: Session,
    student_id,
    clock: Clock,
    call_count: int,
) -> dict:
    if call_count >= 3:
        _record_security_event(db, student_id, "tool_call_limit_exceeded")
        return {"error": "tool_call_limit"}
    return execute_tool(call.name, call.args, db, student_id, clock)


def stream_message(
    db: Session,
    conversation: Conversation,
    profile: StudentProfile,
    raw_text: str,
    provider: LLMProvider | Callable[[], LLMProvider],
    clock: Clock,
    risk_hook: Callable[[str, object], None] | None = None,
) -> Iterator[dict]:
    sanitized = sanitize_message(raw_text)
    student_id = conversation.student_id
    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=sanitized.text,
            redaction_flags=sanitized.redaction_flags,
        )
    )
    db.commit()

    if detect_prompt_injection(sanitized.text):
        _record_security_event(db, student_id, "prompt_injection_heuristic")
        db.commit()
    if risk_hook:
        risk_hook(sanitized.text, student_id)

    today = clock.now().date()
    usage = _daily_usage(db, student_id, today)
    if (usage.tokens if usage else 0) >= settings.max_daily_tokens_per_student:
        answer = FRIENDLY_TOKEN_LIMIT
        _persist_assistant(db, conversation.id, answer)
        db.commit()
        yield {"event": "delta", "data": answer}
        yield {"event": "done", "data": {}}
        return

    system, messages = build_context(db, conversation, profile, sanitized.text, clock)
    all_text: list[str] = []
    stream_buffer = ""
    stream_canary_detected = False
    streamed_chars = 0
    total_calls = 0
    input_tokens = 0
    output_tokens = 0
    try:
        llm = provider() if callable(provider) else provider
        for _ in range(5):
            round_text: list[str] = []
            calls: list[ToolCall] = []
            for event in llm.stream_chat(system, messages, tool_specs()):
                if isinstance(event, TextDelta):
                    round_text.append(event.text)
                    all_text.append(event.text)
                    stream_buffer += event.text
                    raw_output = "".join(all_text)
                    if CANARY in raw_output:
                        stream_canary_detected = True
                        stream_buffer = ""
                    elif not stream_canary_detected:
                        safe_length = _safe_prefix_length(stream_buffer)
                        if safe_length:
                            safe_prefix = sanitize_model_output(stream_buffer[:safe_length])
                            safe_prefix = safe_prefix[: max(MAX_OUTPUT_CHARS - streamed_chars, 0)]
                            if safe_prefix:
                                streamed_chars += len(safe_prefix)
                                yield {"event": "delta", "data": safe_prefix}
                            stream_buffer = stream_buffer[safe_length:]
                elif isinstance(event, ToolCall):
                    calls.append(event)
                elif isinstance(event, Usage):
                    input_tokens += event.input_tokens
                    output_tokens += event.output_tokens
            if not calls:
                break

            assistant_calls = []
            tool_messages = []
            for call in calls:
                call_id = call.call_id or f"call_{total_calls + 1}"
                result = _safe_tool_result(call, db, student_id, clock, total_calls)
                if total_calls < 3:
                    total_calls += 1
                assistant_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.args, ensure_ascii=False),
                        },
                    }
                )
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": call.name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                yield {"event": "tool", "name": call.name}
            messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": "".join(round_text) or None,
                        "tool_calls": assistant_calls,
                    },
                    *tool_messages,
                ]
            )
            db.flush()
        output = "".join(all_text)
        if CANARY in output:
            _record_security_event(db, student_id, "llm_canary_leak")
            output = CANARY_RESPONSE
        else:
            output = sanitize_model_output(output)
        if not output:
            output = "Estou aqui com você. Qual é o próximo passo que parece possível hoje?"
        if input_tokens == 0 and output_tokens == 0:
            input_tokens = max(
                1, (len(system) + len(json.dumps(messages, ensure_ascii=False))) // 4
            )
            output_tokens = max(1, len(output) // 4)
        _add_usage(db, student_id, today, input_tokens + output_tokens)
        _persist_assistant(db, conversation.id, output)
        db.commit()
        for start in range(0, len(output), 160):
            yield {
                "event": "delta",
                "data": output[start : start + 160],
                "replace": start == 0,
            }
        yield {"event": "done", "data": {"tokens": input_tokens + output_tokens}}
    except Exception:
        db.rollback()
        yield {"event": "error", "data": FRIENDLY_PROVIDER_ERROR}
