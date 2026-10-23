import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class SanitizedMessage:
    text: str
    redaction_flags: dict[str, bool]


_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_RG = re.compile(r"(?<!\d)\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx](?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE = re.compile(
    r"(?<!\d)(?:\+?55[\s().-]?)?(?:\(?\d{2}\)?[\s.-]?)?(?:9\d{4}|\d{4})[\s.-]?\d{4}(?!\d)"
)
_BANK = re.compile(
    r"\b(?:ag(?:ê|e)ncia|ag\.?)\s*(?:n[ºo.]?\s*)?\d{1,6}(?:[-/.]\d)?"
    r"\s*(?:,|/|\be\b|[-–])?\s*conta\s*(?:corrente|poupança|poupanca)?"
    r"\s*(?:n[ºo.]?\s*)?\d{3,15}(?:[-/.]\d{1,2})?\b",
    re.IGNORECASE,
)


def _has_luhn(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _clean_unicode(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    cleaned = []
    for char in normalized:
        codepoint = ord(char)
        if 0xE0000 <= codepoint <= 0xE007F:
            continue
        if char != "\n" and unicodedata.category(char) in {"Cc", "Cf", "Cs"}:
            continue
        cleaned.append(char)
    return "".join(cleaned)


def sanitize_message(value: str) -> SanitizedMessage:
    text = _clean_unicode(value)[:2000]
    flags: dict[str, bool] = {}

    def replace(pattern: re.Pattern, label: str, key: str, predicate=None) -> None:
        nonlocal text

        def substitute(match: re.Match) -> str:
            if predicate and not predicate(match.group(0)):
                return match.group(0)
            flags[key] = True
            return label

        text = pattern.sub(substitute, text)

    replace(_BANK, "[conta bancária removida]", "bank_account")
    replace(_CPF, "[CPF removido]", "cpf")
    replace(_RG, "[RG removido]", "rg")
    replace(
        _CARD,
        "[cartão removido]",
        "card",
        lambda value: _has_luhn(re.sub(r"\D", "", value)),
    )
    replace(_EMAIL, "[e-mail removido]", "email")

    def is_brazilian_phone(value: str) -> bool:
        digits = re.sub(r"\D", "", value)
        return len(digits) in {10, 11, 12, 13}

    replace(_PHONE, "[telefone removido]", "phone", is_brazilian_phone)
    return SanitizedMessage(text=text[:2000], redaction_flags=flags)


def detect_prompt_injection(value: str) -> bool:
    patterns = (
        r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b",
        r"\bignore\s+(?:as\s+)?instruções\b",
        r"\ba\s+partir\s+de\s+agora\b",
        r"\b(?:prompt|system|sistema)\s*:",
        r"\b(?:reveal|mostre|revele)\s+(?:the\s+)?(?:system|instruções?)\b",
    )
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)
