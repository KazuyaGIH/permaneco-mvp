import json
import logging
import re
from collections.abc import Callable, Iterator
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.context import CANARY, build_context
from app.ai.providers.base import (
    LLMProvider,
    ProviderUnavailableError,
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
logger = logging.getLogger("app.ai")


def _provider_error_details(error: Exception) -> tuple[int | None, str | None]:
    current: BaseException | None = error
    visited: set[int] = set()
    http_status = None
    provider_code = None
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(current, "status_code", None) or getattr(response, "status_code", None)
        code = getattr(current, "code", None)
        status_label = getattr(current, "status", None)
        if http_status is None and isinstance(status, int):
            http_status = status
        if http_status is None and isinstance(code, int) and 100 <= code <= 599:
            http_status = code
        for value in (code, status_label):
            if (
                provider_code is None
                and isinstance(value, str)
                and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value)
            ):
                provider_code = value
        current = current.__cause__ or current.__context__
    return http_status, provider_code


def _message_for_token_estimate(message: dict) -> dict:
    cleaned = {
        key: value for key, value in message.items() if key not in {"provider_data", "text_parts"}
    }
    if isinstance(cleaned.get("tool_calls"), list):
        cleaned["tool_calls"] = [
            {key: value for key, value in call.items() if key != "provider_data"}
            for call in cleaned["tool_calls"]
        ]
    return cleaned


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
    yield {"event": "user_message", "data": {"content": sanitized.text}}

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
        turn_model = None
        for _ in range(5):
            round_text: list[str] = []
            round_text_parts: list[dict] = []
            has_text_provider_data = False
            calls: list[ToolCall] = []
            stream = (
                llm.stream_chat(system, messages, tool_specs())
                if turn_model is None
                else llm.stream_chat(system, messages, tool_specs(), model=turn_model)
            )
            for event in stream:
                if isinstance(event, TextDelta):
                    round_text.append(event.text)
                    text_part = {"text": event.text}
                    if event.provider_data is not None:
                        text_part["provider_data"] = event.provider_data
                        has_text_provider_data = True
                    round_text_parts.append(text_part)
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
                    if event.model is not None:
                        turn_model = event.model
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
                        "provider_data": call.provider_data,
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
            assistant_message = {
                "role": "assistant",
                "content": "".join(round_text) or None,
                "tool_calls": assistant_calls,
            }
            if has_text_provider_data:
                assistant_message["text_parts"] = round_text_parts
            messages.extend([assistant_message, *tool_messages])
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
                1,
                (
                    len(system)
                    + len(
                        json.dumps(
                            [_message_for_token_estimate(message) for message in messages],
                            ensure_ascii=False,
                        )
                    )
                )
                // 4,
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
    except Exception as error:
        log_fields = [f"exception_class={type(error).__name__}"]
        if isinstance(error, ProviderUnavailableError):
            http_status, provider_code = _provider_error_details(error)
            if http_status is not None:
                log_fields.append(f"http_status={http_status}")
            if provider_code is not None:
                log_fields.append(f"provider_code={provider_code}")
        logger.error("AI stream failed %s", " ".join(log_fields))
        db.rollback()
        yield {"event": "error", "data": FRIENDLY_PROVIDER_ERROR}
