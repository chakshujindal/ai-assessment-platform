"""Recruiter sign-up and sign-in (email + password -> JWT)."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.deps import CurrentRecruiter, DbSession, SettingsDep
from app.models import Recruiter
from app.ratelimit import AUTH_LIMIT, DEFAULT_LIMIT, limiter
from app.schemas import Credentials, TokenOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_for(recruiter: Recruiter, settings: SettingsDep) -> TokenOut:
    token = create_access_token(recruiter.id, settings.jwt_secret, settings.jwt_ttl_minutes)
    return TokenOut(access_token=token, email=recruiter.email)


@router.post("/register", status_code=201)
@limiter.limit(AUTH_LIMIT)
def register(request: Request, body: Credentials, db: DbSession, settings: SettingsDep) -> TokenOut:
    email = body.email.lower()
    if db.scalar(select(Recruiter).where(Recruiter.email == email)):
        raise HTTPException(409, "That email is already registered.")
    recruiter = Recruiter(email=email, password_hash=hash_password(body.password))
    db.add(recruiter)
    db.commit()
    return _token_for(recruiter, settings)


@router.post("/login")
@limiter.limit(AUTH_LIMIT)
def login(request: Request, body: Credentials, db: DbSession, settings: SettingsDep) -> TokenOut:
    recruiter = db.scalar(select(Recruiter).where(Recruiter.email == body.email.lower()))
    if recruiter is None or not verify_password(recruiter.password_hash, body.password):
        raise HTTPException(401, "Wrong email or password.")
    return _token_for(recruiter, settings)


@router.get("/me")
@limiter.limit(DEFAULT_LIMIT)
def me(request: Request, recruiter: CurrentRecruiter) -> dict[str, str]:
    return {"email": recruiter.email}
