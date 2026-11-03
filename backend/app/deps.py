"""FastAPI dependencies: DB session, settings, LLM client, and the signed-in recruiter."""

from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.llm.base import LLMClient
from app.models import Recruiter
from app.security import decode_access_token


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm


DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
LLMDep = Annotated[LLMClient, Depends(get_llm)]

_bearer = HTTPBearer(auto_error=False)


def current_recruiter(
    db: DbSession,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Recruiter:
    unauthorized = HTTPException(
        401, "Please sign in again.", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        recruiter_id = decode_access_token(credentials.credentials, settings.jwt_secret)
    except jwt.InvalidTokenError as exc:
        raise unauthorized from exc
    recruiter = db.get(Recruiter, recruiter_id)
    if recruiter is None:
        raise unauthorized
    return recruiter


CurrentRecruiter = Annotated[Recruiter, Depends(current_recruiter)]
