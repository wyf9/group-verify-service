from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Boolean, Integer, String, Text, create_engine, func, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import BASE_DIR, settings


def _database_url() -> str:
    url = settings.database
    if url.startswith("sqlite:///./"):
        rel = url.removeprefix("sqlite:///./")
        path = BASE_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return url


engine = create_engine(
    _database_url(),
    connect_args={"check_same_thread": False} if settings.database.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class VerifyTicket(Base):
    __tablename__ = "GeetestTable"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)
    expire_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    verified_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, default=lambda: int(time.time())
    )
    updated_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    note: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ApiCallLog(Base):
    __tablename__ = "api_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ticket: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


class VerifyLog(Base):
    __tablename__ = "verify_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ticket: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


def _ensure_columns() -> None:
    """为已存在的旧数据库补齐新增列（轻量迁移）。"""
    inspector = inspect(engine)
    if "api_keys" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("api_keys")}
    migrations = {
        "note": "ALTER TABLE api_keys ADD COLUMN note VARCHAR(255) NOT NULL DEFAULT ''",
        "enabled": "ALTER TABLE api_keys ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1",
        "last_used_at": "ALTER TABLE api_keys ADD COLUMN last_used_at INTEGER",
        "request_count": "ALTER TABLE api_keys ADD COLUMN request_count INTEGER NOT NULL DEFAULT 0",
    }
    import contextlib

    with engine.begin() as conn:
        for column, ddl in migrations.items():
            if column not in existing:
                with contextlib.suppress(Exception):
                    conn.execute(text(ddl))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    with SessionLocal() as db:
        keys = normalize_api_keys(settings.api_key)
        if keys and db.query(ApiKey).count() == 0:
            ts = int(time.time())
            db.add_all([ApiKey(hash=sha256_hex(k), created_at=ts, updated_at=ts) for k in keys])
            db.commit()


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sha256_hex(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_api_keys(raw: str | list[str]) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    value = str(raw).strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        import json

        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(x).strip() for x in decoded if str(x).strip()]
        except json.JSONDecodeError:
            pass
    import re

    return [x for x in re.split(r"[,\s;，；]+", value) if x]


def setting_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.name == key).first()
    if row is not None:
        return row.value
    return default


def upsert_setting(db: Session, key: str, value: str) -> None:
    ts = int(time.time())
    row = db.query(Setting).filter(Setting.name == key).first()
    if row is None:
        db.add(Setting(name=key, value=value, created_at=ts, updated_at=ts))
    else:
        row.value = value
        row.updated_at = ts


def count_rows(db: Session, model: type[Any], *criteria: Any) -> int:
    return int(db.query(func.count(cast(Any, model).id)).filter(*criteria).scalar() or 0)


def touch_api_key(db: Session, api_key_id: int | None) -> None:
    """记录 API Key 最后使用时间并累加验证请求数。"""
    if not api_key_id or api_key_id <= 0:
        return
    try:
        db.query(ApiKey).filter(ApiKey.id == api_key_id).update(
            {
                "last_used_at": int(time.time()),
                "request_count": ApiKey.request_count + 1,
            }
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
