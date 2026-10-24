import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


def _decode_key(value: str) -> bytes:
    try:
        key = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("Encryption keys must be valid base64.") from error
    if len(key) != 32:
        raise ValueError("AES-GCM encryption keys must contain 32 bytes.")
    return key


def _keyring() -> dict[str, bytes]:
    raw_keyring = os.getenv("DATA_ENCRYPTION_KEYS", "")
    keys: dict[str, bytes] = {}
    if raw_keyring:
        parsed = json.loads(raw_keyring)
        if not isinstance(parsed, dict):
            raise ValueError("DATA_ENCRYPTION_KEYS must be a JSON object.")
        keys = {key_id: _decode_key(value) for key_id, value in parsed.items()}
    legacy_key = os.getenv("DATA_ENCRYPTION_KEY")
    active_id = os.getenv("DATA_ENCRYPTION_KEY_ID", "default")
    if legacy_key and active_id not in keys:
        keys[active_id] = _decode_key(legacy_key)
    if not keys:
        raise ValueError("Configure DATA_ENCRYPTION_KEY or DATA_ENCRYPTION_KEYS.")
    return keys


def encrypt(plaintext: str) -> str:
    active_id = os.getenv("DATA_ENCRYPTION_KEY_ID", "default")
    keys = _keyring()
    if active_id not in keys:
        raise ValueError("The active encryption key id is not present in the keyring.")
    nonce = os.urandom(12)
    encrypted = AESGCM(keys[active_id]).encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = base64.b64encode(nonce + encrypted).decode("ascii")
    return f"v1:{active_id}:{payload}"


def decrypt(ciphertext: str) -> str:
    version, key_id, payload = ciphertext.split(":", maxsplit=2)
    if version != "v1":
        raise ValueError("Unsupported ciphertext version.")
    keys = _keyring()
    if key_id not in keys:
        raise ValueError(f"Encryption key id {key_id!r} is not available.")
    raw = base64.b64decode(payload, validate=True)
    nonce, encrypted = raw[:12], raw[12:]
    if len(nonce) != 12 or not encrypted:
        raise ValueError("Ciphertext payload is malformed.")
    return AESGCM(keys[key_id]).decrypt(nonce, encrypted, None).decode("utf-8")


class EncryptedText(TypeDecorator[str]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return encrypt(value)

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return decrypt(value)
