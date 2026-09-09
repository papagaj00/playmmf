from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app import models

SESSION_COOKIE = "gbn_session"
SESSION_DAYS = 14
password_hash = PasswordHash.recommended()


def hash_password(value: str) -> str:
    return password_hash.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    return password_hash.verify(value, hashed)


def new_session(db: Session, user: models.User) -> str:
    raw_token = secrets.token_urlsafe(32)
    session = models.Session(
        user_id=user.id,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS),
    )
    db.add(session)
    db.commit()
    return raw_token


def get_user_from_token(db: Session, raw_token: str | None) -> models.User:
    if not raw_token:
        raise HTTPException(status_code=401, detail="Přihlášení je vyžadováno.")
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session = (
        db.query(models.Session)
        .filter(models.Session.token_hash == token_hash, models.Session.revoked_at.is_(None))
        .first()
    )
    if session is None:
        raise HTTPException(status_code=401, detail="Přihlášení vypršelo.")
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise HTTPException(status_code=401, detail="Přihlášení vypršelo.")
    return session.user


def current_user(
    db: Session, gbn_session: str | None = Cookie(default=None)
) -> models.User:
    return get_user_from_token(db, gbn_session)