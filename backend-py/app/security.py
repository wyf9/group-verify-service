from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from .db import ApiKey, sha256_hex


@dataclass(frozen=True)
class AuthContext:
    api_key_id: int
    is_default: bool


def default_api_key_id(db: Session) -> int:
    row = db.query(ApiKey).order_by(ApiKey.id.asc()).first()
    return int(row.id) if row else 0


def authenticate(db: Session, authorization: str | None = Header(default=None)) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "msg": "Unauthorized: Invalid Authorization header format"},
        )
    value = authorization.removeprefix("Bearer ").strip()
    if not value:
        raise HTTPException(
            status_code=401, detail={"code": 401, "msg": "Unauthorized: Invalid API key"}
        )
    key_hash = sha256_hex(value)
    for row in db.query(ApiKey).all():
        if secrets.compare_digest(row.hash, key_hash):
            if not row.enabled:
                raise HTTPException(
                    status_code=401,
                    detail={"code": 401, "msg": "Unauthorized: API key disabled"},
                )
            default_id = default_api_key_id(db)
            return AuthContext(
                api_key_id=row.id, is_default=default_id > 0 and row.id == default_id
            )
    raise HTTPException(
        status_code=401, detail={"code": 401, "msg": "Unauthorized: Invalid API key"}
    )


def require_default(ctx: AuthContext) -> None:
    if not ctx.is_default:
        raise HTTPException(
            status_code=403,
            detail={"code": 403, "msg": "权限不足：该接口仅允许默认 API Key 调用"},
        )


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "******"
    return f"{value[:4]}...{value[-4:]}"
