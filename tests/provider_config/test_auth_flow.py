from __future__ import annotations

import base64
import hashlib
from unittest.mock import MagicMock, patch
from urllib import parse

import pytest

from marius.provider_config.auth_flow import (
    CHATGPT_AUTHORIZE_URL,
    CHATGPT_CLIENT_ID,
    CHATGPT_REDIRECT_URI,
    ChatGPTOAuthFlow,
    OAuthError,
    OAuthTokenResult,
    _OAuthCallbackHandler,
    build_authorize_url,
    exchange_code,
    generate_pkce,
    refresh_token,
)


# ── generate_pkce ─────────────────────────────────────────────────────────────


def test_generate_pkce_returns_two_non_empty_strings():
    verifier, challenge = generate_pkce()
    assert isinstance(verifier, str) and verifier
    assert isinstance(challenge, str) and challenge


def test_generate_pkce_challenge_is_sha256_of_verifier():
    verifier, challenge = generate_pkce()
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert challenge == expected


def test_generate_pkce_challenge_has_no_padding():
    _, challenge = generate_pkce()
    assert "=" not in challenge


def test_generate_pkce_produces_unique_pairs():
    pairs = {generate_pkce() for _ in range(5)}
    assert len(pairs) == 5


# ── build_authorize_url ───────────────────────────────────────────────────────


def _parse_url_params(url: str) -> dict[str, str]:
    qs = parse.urlparse(url).query
    return {k: v[0] for k, v in parse.parse_qs(qs).items()}


def test_build_authorize_url_starts_with_authorize_endpoint():
    url = build_authorize_url(code_challenge="abc", state="xyz")
    assert url.startswith(CHATGPT_AUTHORIZE_URL)


def test_build_authorize_url_contains_required_params():
    url = build_authorize_url(code_challenge="mychallenge", state="mystate")
    params = _parse_url_params(url)
    assert params["client_id"] == CHATGPT_CLIENT_ID
    assert params["code_challenge"] == "mychallenge"
    assert params["state"] == "mystate"
    assert params["response_type"] == "code"
    assert params["redirect_uri"] == CHATGPT_REDIRECT_URI


def test_build_authorize_url_method_is_s256():
    url = build_authorize_url(code_challenge="c", state="s")
    assert _parse_url_params(url)["code_challenge_method"] == "S256"


def test_build_authorize_url_originator_is_marius():
    url = build_authorize_url(code_challenge="c", state="s")
    assert _parse_url_params(url)["originator"] == "marius"


def test_build_authorize_url_custom_redirect_uri():
    url = build_authorize_url(
        code_challenge="c",
        state="s",
        redirect_uri="http://localhost:9999/cb",
    )
    assert _parse_url_params(url)["redirect_uri"] == "http://localhost:9999/cb"


# ── exchange_code ─────────────────────────────────────────────────────────────


def test_exchange_code_sends_authorization_code_grant():
    captured = {}

    def transport(url, payload):
        captured.update(payload)
        return {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600}

    exchange_code("my_code", "my_verifier", "http://localhost/cb", transport=transport)

    assert captured["grant_type"] == "authorization_code"
    assert captured["code"] == "my_code"
    assert captured["code_verifier"] == "my_verifier"
    assert captured["redirect_uri"] == "http://localhost/cb"
    assert captured["client_id"] == CHATGPT_CLIENT_ID


def test_exchange_code_returns_transport_result():
    fake = {"access_token": "abc", "refresh_token": "def", "expires_in": 1000}
    result = exchange_code("c", "v", "uri", transport=lambda url, p: fake)
    assert result == fake


# ── refresh_token ─────────────────────────────────────────────────────────────


def test_refresh_token_sends_refresh_grant():
    captured = {}

    def transport(url, payload):
        captured.update(payload)
        return {"access_token": "new_tok", "expires_in": 3600}

    refresh_token("old_refresh_tok", transport=transport)

    assert captured["grant_type"] == "refresh_token"
    assert captured["refresh_token"] == "old_refresh_tok"
    assert captured["client_id"] == CHATGPT_CLIENT_ID


# ── _OAuthCallbackHandler ─────────────────────────────────────────────────────


def _invoke_handler(path: str, *, expected_state: str) -> tuple[int, str | None]:
    """Appelle do_GET sur un handler isolé et retourne (status, code capturé)."""
    _OAuthCallbackHandler.expected_state = expected_state
    _OAuthCallbackHandler.code = None

    handler = object.__new__(_OAuthCallbackHandler)
    handler.path = path

    statuses: list[int] = []
    handler._respond = lambda status, body: statuses.append(status)
    handler.do_GET()

    return (statuses[0] if statuses else 0), _OAuthCallbackHandler.code


def test_callback_handler_valid_request_sets_code():
    path = "/auth/callback?code=mycode&state=mystate"
    status, code = _invoke_handler(path, expected_state="mystate")
    assert status == 200
    assert code == "mycode"


def test_callback_handler_wrong_path_returns_404():
    path = "/wrong/path?code=x&state=s"
    status, code = _invoke_handler(path, expected_state="s")
    assert status == 404
    assert code is None


def test_callback_handler_state_mismatch_returns_400():
    path = "/auth/callback?code=mycode&state=BAD"
    status, code = _invoke_handler(path, expected_state="GOOD")
    assert status == 400
    assert code is None


def test_callback_handler_missing_code_returns_400():
    path = "/auth/callback?state=mystate"
    status, code = _invoke_handler(path, expected_state="mystate")
    assert status == 400
    assert code is None


# ── ChatGPTOAuthFlow ──────────────────────────────────────────────────────────


@patch("http.server.HTTPServer")
def test_oauth_flow_timeout_raises_oauth_error(mock_server_cls):
    mock_server_cls.return_value = MagicMock()
    flow = ChatGPTOAuthFlow(timeout_seconds=0, token_transport=lambda url, p: {})

    with pytest.raises(OAuthError, match="Timeout"):
        flow.run(on_url=lambda url: None)


@patch("http.server.HTTPServer")
def test_oauth_flow_calls_on_url_with_authorize_url(mock_server_cls):
    mock_server_cls.return_value = MagicMock()
    flow = ChatGPTOAuthFlow(timeout_seconds=0, token_transport=lambda url, p: {})
    urls: list[str] = []

    with pytest.raises(OAuthError):
        flow.run(on_url=urls.append)

    assert len(urls) == 1
    assert urls[0].startswith(CHATGPT_AUTHORIZE_URL)


@patch("http.server.HTTPServer")
def test_oauth_flow_success_returns_token_result(mock_server_cls):
    mock_server = MagicMock()
    mock_server_cls.return_value = mock_server

    calls = [0]

    def fake_handle_request():
        calls[0] += 1
        if calls[0] == 1:
            _OAuthCallbackHandler.code = "auth_code_123"

    mock_server.handle_request = fake_handle_request

    fake_token = {"access_token": "tok_abc", "refresh_token": "ref_xyz", "expires_in": 3600}
    flow = ChatGPTOAuthFlow(
        timeout_seconds=10,
        token_transport=lambda url, payload: fake_token,
    )

    result = flow.run(on_url=lambda url: None)

    assert isinstance(result, OAuthTokenResult)
    assert result.access_token == "tok_abc"
    assert result.refresh_token == "ref_xyz"
    assert result.expires > 0
    assert result.obtained_at


@patch("http.server.HTTPServer")
def test_oauth_flow_server_is_always_closed(mock_server_cls):
    mock_server = MagicMock()
    mock_server_cls.return_value = mock_server

    flow = ChatGPTOAuthFlow(timeout_seconds=0, token_transport=lambda url, p: {})

    with pytest.raises(OAuthError):
        flow.run(on_url=lambda url: None)

    mock_server.server_close.assert_called_once()
