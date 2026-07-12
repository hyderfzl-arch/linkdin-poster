import pytest

import security


def test_encrypt_decrypt_roundtrip():
    original = "super-secret-token"
    encrypted = security.encrypt(original)
    assert encrypted != original
    decrypted = security.decrypt(encrypted)
    assert decrypted == original


def test_encrypt_empty():
    assert security.encrypt("") == ""
    assert security.decrypt("") == ""


def test_encrypt_decrypt_unicode():
    original = "Token with unicode: ñéü 🚀"
    encrypted = security.encrypt(original)
    decrypted = security.decrypt(encrypted)
    assert decrypted == original


def test_decrypt_invalid_token(monkeypatch):
    with pytest.raises(Exception):
        security.decrypt("not-a-valid-fernet-token")


def test_get_fernet_requires_secret_key(monkeypatch):
    monkeypatch.setattr("config.SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="SECRET_KEY is not configured"):
        security._get_fernet()
