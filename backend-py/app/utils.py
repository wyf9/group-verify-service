from __future__ import annotations

import hashlib
import hmac
import secrets
import string
import time
from collections import defaultdict
from typing import Any

import httpx
from fastapi import HTTPException, Request

from .config import settings
from .db import Session, setting_value

_rate_limits: dict[str, list[int]] = defaultdict(list)


def now_ts() -> int:
    return int(time.time())


def rate_limit_hit(key: str, limit: int, window_seconds: int) -> int:
    now = now_ts()
    start = now - window_seconds
    hits = [x for x in _rate_limits[key] if x > start]
    if len(hits) >= limit:
        _rate_limits[key] = hits
        return max(1, hits[0] + window_seconds - now)
    hits.append(now)
    _rate_limits[key] = hits
    return 0


def generate_token(group_id: str, user_id: str, salt: str) -> str:
    raw = f"{group_id}{user_id}{now_ts()}{secrets.token_hex(16)}{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_code() -> str:
    alphabet = string.digits + string.ascii_uppercase
    return "".join(secrets.choice(alphabet) for _ in range(6))


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else ""


def retry_response(retry_after: int, passed: bool | None = None) -> HTTPException:
    body: dict[str, Any] = {"code": 429, "msg": "请求过于频繁，请稍后重试"}
    if passed is not None:
        body["passed"] = passed
    return HTTPException(status_code=429, detail=body, headers={"Retry-After": str(retry_after)})


def geetest_config(db: Session) -> tuple[str, str, str, int, str]:
    captcha_id = setting_value(db, "GEETEST_CAPTCHA_ID", settings.geetest.captcha_id)
    captcha_key = setting_value(db, "GEETEST_CAPTCHA_KEY", settings.geetest.captcha_key)
    api_server = setting_value(db, "GEETEST_API_SERVER", settings.geetest.api_server)
    expire = int(setting_value(db, "GEETEST_CODE_EXPIRE", str(settings.geetest.code_expire)) or 300)
    salt = setting_value(db, "SALT", settings.salt)
    return captcha_id, captcha_key, api_server.rstrip("/"), expire, salt


async def verify_geetest(db: Session, params: dict[str, str]) -> bool:
    captcha_id, captcha_key, api_server, _expire, _salt = geetest_config(db)
    sign_token = hmac.new(
        captcha_key.encode("utf-8"), params["lot_number"].encode("utf-8"), hashlib.sha256
    ).hexdigest()
    data = {
        "lot_number": params["lot_number"],
        "captcha_output": params["captcha_output"],
        "pass_token": params["pass_token"],
        "gen_time": params["gen_time"],
        "sign_token": sign_token,
        "captcha_id": captcha_id,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(
                f"{api_server}/validate", params={"captcha_id": captcha_id}, data=data
            )
            if resp.status_code != 200:
                return False
            return resp.json().get("result") == "success"
        except (httpx.HTTPError, ValueError):
            return False
