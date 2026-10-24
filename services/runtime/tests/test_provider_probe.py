import json

import httpx
import pytest

from media_lab import providers as module
from media_lab.providers import ProviderSettings
from media_lab.security import as_owner
from test_personal_providers import public_dns  # noqa: F401  (fixture)
from test_web_redesign import endpoints
from test_web_security import lab  # noqa: F401  (fixture)


def reasoning_model(seen):
    """OpenRouter-like reasoning model: thinking consumes max_tokens before any answer."""
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if body["max_tokens"] < 500:
            return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": None, "reasoning": "Let me think…"}}]})
        if body.get("tools"):
            return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "1", "type": "function", "function": {"name": "capability_probe", "arguments": {"ok": True}}}]}}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant",
            "content": [{"type": "reasoning", "text": "hidden"}, {"type": "text", "text": "Red"}]}}]})
    return handler


@pytest.fixture
def provider(lab, public_dns, monkeypatch):  # noqa: F811
    app, accounts, _, _, _, alice, _ = lab
    endpoints(accounts)
    with as_owner(alice):
        app.state.providers.save(ProviderSettings(endpoint_id='one', model='stepfun/step-5-preview', api_key='probe-secret-key'))

    def install(handler):
        real = httpx.Client
        monkeypatch.setattr(module.httpx, 'Client', lambda **kw: real(**{**kw, 'transport': httpx.MockTransport(handler)}))
    return app.state.providers, alice, install


def test_reasoning_models_pass_every_probe_and_no_tool_choice_is_sent(provider):
    providers, alice, install = provider
    seen = []
    install(reasoning_model(seen))
    with as_owner(alice):
        result = providers._test()
    assert (result["chat"], result["tools"], result["vision"]) == (True, True, True), result["errors"]
    assert all(body["max_tokens"] >= 2048 for body in seen)
    assert "tool_choice" not in json.dumps(seen) and any(body.get("tools") for body in seen)


def test_failures_keep_a_specific_secret_free_reason(provider):
    providers, alice, install = provider
    def handler(request):
        if json.loads(request.content).get("tools"):
            return httpx.Response(404, json={"error": {"message": "No endpoints found that support tool use (key probe-secret-key)"}})
        return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": ""}}]})
    install(handler)
    with as_owner(alice):
        result = providers._test()
    assert not any(result[name] for name in ("chat", "tools", "vision"))
    assert "HTTP 404" in result["errors"]["tools"] and "tool use" in result["errors"]["tools"]
    assert "probe-secret-key" not in json.dumps(result)
    assert "límite de tokens" in result["errors"]["chat"]


def test_openrouter_error_bodies_with_status_200_are_reported(provider):
    providers, alice, install = provider
    install(lambda request: httpx.Response(200, json={"error": {"message": "Provider returned error", "code": 502}}))
    with as_owner(alice):
        with pytest.raises(ValueError, match="Provider returned error"):
            providers.chat([{"role": "user", "content": "hi"}])
