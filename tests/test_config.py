import pytest
from pydantic import ValidationError

from app.config import Settings


def _make(monkeypatch, **env) -> Settings:
    """构造一个不读真实 .env 的 Settings，便于精确控制输入。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-123")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


def test_defaults(monkeypatch) -> None:
    s = _make(monkeypatch)
    assert s.deepseek_model == "deepseek-chat"
    assert s.max_tokens == 1024
    assert isinstance(s.max_tokens, int)


def test_secret_is_masked(monkeypatch) -> None:
    s = _make(monkeypatch)
    assert "sk-test-123" not in str(s)
    assert "sk-test-123" not in repr(s)
    assert s.deepseek_api_key.get_secret_value() == "sk-test-123"


def test_missing_key_fails(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_key_fails(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_temperature_out_of_range(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-123")
    monkeypatch.setenv("TEMPERATURE", "5")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_type_coercion(monkeypatch) -> None:
    s = _make(monkeypatch, MAX_TOKENS="512")
    assert s.max_tokens == 512
    assert isinstance(s.max_tokens, int)
