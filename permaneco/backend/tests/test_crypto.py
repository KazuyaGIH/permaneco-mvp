import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.security.crypto import decrypt, encrypt


def encode_key(seed: int) -> str:
    return base64.b64encode(bytes([seed]) * 32).decode("ascii")


def test_encryption_roundtrip(monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", encode_key(1))
    monkeypatch.setenv("DATA_ENCRYPTION_KEYS", "")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_ID", "legacy")
    encrypted = encrypt("Conteúdo sintético protegido.")
    assert encrypted.startswith("v1:legacy:")
    assert decrypt(encrypted) == "Conteúdo sintético protegido."


def test_key_rotation_keeps_old_ciphertext_readable(monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", encode_key(1))
    monkeypatch.setenv("DATA_ENCRYPTION_KEYS", '{"k1":"' + encode_key(1) + '"}')
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_ID", "k1")
    old_ciphertext = encrypt("Texto antigo.")

    monkeypatch.setenv(
        "DATA_ENCRYPTION_KEYS",
        '{"k1":"' + encode_key(1) + '","k2":"' + encode_key(2) + '"}',
    )
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_ID", "k2")
    new_ciphertext = encrypt("Texto novo.")

    assert old_ciphertext.startswith("v1:k1:")
    assert new_ciphertext.startswith("v1:k2:")
    assert decrypt(old_ciphertext) == "Texto antigo."
    assert decrypt(new_ciphertext) == "Texto novo."


def test_tampering_is_detected(monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", encode_key(3))
    monkeypatch.setenv("DATA_ENCRYPTION_KEYS", "")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_ID", "k3")
    ciphertext = encrypt("Texto autenticado.")
    version, key_id, payload = ciphertext.split(":")
    raw = bytearray(base64.b64decode(payload))
    raw[0] ^= 1
    altered = f"{version}:{key_id}:{base64.b64encode(raw).decode('ascii')}"
    with pytest.raises(InvalidTag):
        decrypt(altered)
