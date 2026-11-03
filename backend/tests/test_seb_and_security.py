from datetime import timedelta

import jwt
import pytest

from app.db import utcnow
from app.seb import public_url, request_hash, verify_request_hash
from app.security import (
    create_access_token,
    decode_access_token,
    hash_invite_token,
    hash_password,
    new_invite_token,
    verify_password,
)

URL = "https://exams.example.com/api/take/abc123"
BEK = "0f2c7c3e5b8d4a6f9e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5b6a7f8e9d0c1b2a3f"
# sha256(URL + BEK), computed once and pinned so a refactor cannot silently change it.
EXPECTED = "60252aa11a652f770d4f384e1853a48e891a803b690bf411e4de347c08745d50"


def test_request_hash_matches_pinned_vector() -> None:
    assert request_hash(URL, BEK) == EXPECTED


def test_fragment_is_ignored() -> None:
    assert request_hash(URL + "#question-3", BEK) == EXPECTED


def test_verify_accepts_matching_header_in_any_case() -> None:
    assert verify_request_hash(URL, BEK, EXPECTED)
    assert verify_request_hash(URL, BEK, f" {EXPECTED.upper()} ")


@pytest.mark.parametrize(
    ("url", "key", "header"),
    [
        (URL, BEK, None),
        (URL, BEK, ""),
        (URL, "", EXPECTED),
        (URL, BEK[:-1] + "0", EXPECTED),
        (URL + "?page=2", BEK, EXPECTED),
        ("http://exams.example.com/api/take/abc123", BEK, EXPECTED),
    ],
)
def test_verify_rejects_anything_else(url: str, key: str, header: str | None) -> None:
    assert not verify_request_hash(url, key, header)


def test_public_url_rewrites_origin_but_keeps_path_and_query() -> None:
    seen = "http://127.0.0.1:8000/api/take/abc123?x=1"
    assert public_url(seen, "") == seen
    assert public_url(seen, "https://exams.example.com/") == URL + "?x=1"


def test_password_hashing() -> None:
    hashed = hash_password("correct horse")
    assert hashed.startswith("$argon2")
    assert verify_password(hashed, "correct horse")
    assert not verify_password(hashed, "wrong horse")
    assert not verify_password("not-a-hash", "anything")


SECRET = "a-test-secret-of-at-least-32-bytes"


def test_jwt_roundtrip_and_expiry() -> None:
    token = create_access_token(7, SECRET, ttl_minutes=5)
    assert decode_access_token(token, SECRET) == 7
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, SECRET.upper())
    old = create_access_token(7, SECRET, ttl_minutes=5, now=utcnow() - timedelta(hours=1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(old, SECRET)


def test_invite_tokens_are_random_and_only_hashed() -> None:
    token, token_hash = new_invite_token()
    other, _ = new_invite_token()
    assert token != other and len(token) >= 40
    assert token_hash == hash_invite_token(token) != token
