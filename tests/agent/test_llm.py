from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

import app.agent.llm as llm_module


def test_build_llm_reads_environment_and_configures_prompt_caching(monkeypatch, caplog):
    client = Mock()
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test-model")
    monkeypatch.setattr(llm_module, "ChatOpenAI", client)
    load_dotenv = Mock()
    monkeypatch.setattr(llm_module, "load_dotenv", load_dotenv)

    result = llm_module.build_llm()

    assert result is client.return_value
    load_dotenv.assert_called_once_with()
    client.assert_called_once_with(
        api_key="test-secret-key",
        model="gpt-test-model",
        temperature=0,
        model_kwargs={"prompt_cache_key": "promtior-booking-agent-v1"},
    )
    assert "test-secret-key" not in caplog.text


def test_build_llm_uses_default_model_when_environment_value_is_unset(monkeypatch):
    client = Mock()
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr(llm_module, "ChatOpenAI", client)
    monkeypatch.setattr(llm_module, "load_dotenv", Mock())

    llm_module.build_llm()

    assert client.call_args.kwargs["model"] == "gpt-4o-mini"


def test_build_system_prompt_contains_grounded_gmt3_turn_context():
    current_dt = datetime(
        2026, 7, 17, 22, 15, tzinfo=timezone(timedelta(hours=-3))
    )

    prompt = llm_module.build_system_prompt(current_dt, "User1")

    assert "Cubo Itaú" in prompt
    assert "Promtior's meeting-room booking assistant" not in prompt
    assert "User1" in prompt
    assert "2026-07-17" in prompt
    assert "2026-07-18" in prompt
    assert "22:15" in prompt
    assert "GMT-3" in prompt
    assert "-03:00" in prompt
    assert "24-hour" in prompt
    assert "rooms A-E" in prompt
    assert "refuse" in prompt.lower()
    assert "availability" in prompt
    assert "capacity" in prompt
    assert "bookings" in prompt
    assert "tool call" in prompt
    assert "never invent" in prompt.lower()
    assert "GMT-3 ISO datetimes" in prompt
    assert "Never convert a datetime to another offset" in " ".join(prompt.split())
    assert prompt == llm_module.build_system_prompt(current_dt, "User1")


@pytest.mark.parametrize(
    "current_dt",
    [datetime(2026, 7, 17, 9, 30), datetime(2026, 7, 17, 12, 30, tzinfo=UTC)],
    ids=["offsetless", "foreign_offset"],
)
def test_build_system_prompt_rejects_non_gmt3_datetime(current_dt):
    with pytest.raises(ValueError, match="GMT-3"):
        llm_module.build_system_prompt(current_dt, "User2")
