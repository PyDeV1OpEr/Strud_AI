"""JWT verification and identity-forcing regression tests."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from strud.backend import auth
from strud.backend.api import main
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def configured_hs256(monkeypatch):
    monkeypatch.setattr(auth, "AUTH_CONFIGURED", True)
    monkeypatch.setattr(auth, "SUPABASE_JWT_SECRET", "test-secret-with-at-least-thirty-two-bytes")
    monkeypatch.setattr(auth, "JWT_ISSUER", "https://example.supabase.co/auth/v1")


def token(**claims: object) -> str:
    payload: dict[str, object] = {
        "sub": "user-a",
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    payload.update(claims)
    return jwt.encode(payload, "test-secret-with-at-least-thirty-two-bytes", algorithm="HS256")


def test_valid_supabase_style_token_returns_verified_subject():
    assert auth.verify_access_token(token()) == "user-a"


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "someone-else"},
        {"iss": "https://attacker.invalid/auth/v1"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"sub": ""},
    ],
)
def test_invalid_claims_are_rejected(claims: dict[str, object]):
    with pytest.raises(HTTPException) as error:
        auth.verify_access_token(token(**claims))
    assert error.value.status_code == 401


def test_backend_overrides_a_forged_user_id(monkeypatch):
    """A bearer subject, not a URL parameter, selects backend data."""
    seen: list[str] = []

    class Store:
        def list_chats(self, user_id: str, deleted: bool = False):
            seen.append(user_id)
            return []

    monkeypatch.setattr(main, "AUTH_CONFIGURED", True)
    monkeypatch.setattr(main, "verify_access_token", lambda _token: "user-a")
    monkeypatch.setattr(main, "get_memory_store", lambda: Store())
    client = TestClient(main.app)

    denied = client.get("/api/chats?user_id=user-b")
    assert denied.status_code == 401
    allowed = client.get(
        "/api/chats?user_id=user-b",
        headers={"Authorization": "Bearer a-valid-token"},
    )
    assert allowed.status_code == 200
    assert seen == ["user-a"]
