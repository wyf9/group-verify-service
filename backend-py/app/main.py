from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager
from math import ceil
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import BASE_DIR, settings
from .db import (
    ApiCallLog,
    ApiKey,
    SessionLocal,
    Setting,
    VerifyTicket,
    count_rows,
    get_db,
    init_db,
    normalize_api_keys,
    sha256_hex,
    upsert_setting,
)
from .schemas import (
    ApiKeyCreateRequest,
    ApiResponse,
    SettingsUpdateRequest,
    VerifyCallbackRequest,
    VerifyCallbackResponse,
    VerifyCheckRequest,
    VerifyCheckResponse,
    VerifyCreateRequest,
    VerifyCreateResponse,
    VerifyStatusResponse,
)
from .security import AuthContext, authenticate, default_api_key_id, mask_secret, require_default
from .utils import (
    client_ip,
    geetest_config,
    generate_code,
    generate_token,
    now_ts,
    rate_limit_hit,
    retry_response,
    verify_geetest,
)

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="group-verify-service API",
    description="入群极验验证后端服务，兼容原 ThinkPHP API。",
    version="0.1.0",
    docs_url="/docs" if settings.enable_doc else None,
    redoc_url="/redoc" if settings.enable_doc else None,
    openapi_url="/openapi.json" if settings.enable_doc else None,
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def api_http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, _exc: RequestValidationError):
    return JSONResponse({"code": 400, "msg": "参数错误"}, status_code=400)


@app.middleware("http")
async def log_api_calls(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith(("/verify", "/admin")):
        try:
            with SessionLocal() as db:
                db.add(
                    ApiCallLog(
                        api_key_id=getattr(request.state, "api_key_id", None),
                        endpoint=request.url.path,
                        method=request.method,
                        status_code=response.status_code,
                        group_id=getattr(request.state, "group_id", None),
                        user_id=getattr(request.state, "user_id", None),
                        ticket=getattr(request.state, "ticket", None),
                        code=getattr(request.state, "code", None),
                        ip=client_ip(request),
                        user_agent=request.headers.get("user-agent", ""),
                        duration_ms=int((time.perf_counter() - start) * 1000),
                        created_at=now_ts(),
                    )
                )
                db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug("failed to log api call: %s", exc)
    return response


async def get_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    form = await request.form()
    return dict(form)


async def current_auth(request: Request, db: Annotated[Session, Depends(get_db)]) -> AuthContext:
    ctx = authenticate(db, request.headers.get("authorization"))
    request.state.api_key_id = ctx.api_key_id
    return ctx


def json_error(status: int, msg: str, **extra: Any) -> None:
    raise HTTPException(status_code=status, detail={"code": status, "msg": msg, **extra})


@app.post(
    "/verify/create",
    response_model=VerifyCreateResponse,
    summary="生成验证链接",
    description=(
        "机器人使用 API Key 为指定群和用户生成一次性验证 ticket 与短链接。支持 JSON 或表单提交。"
    ),
)
async def verify_create(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(current_auth)],
):
    retry = rate_limit_hit(f"rl:verify_create:api:{auth.api_key_id}", 120, 60)
    if retry:
        raise retry_response(retry)
    payload = VerifyCreateRequest.model_validate(await get_payload(request))
    request.state.group_id = payload.group_id
    request.state.user_id = payload.user_id
    if not payload.group_id or not payload.user_id:
        json_error(400, "参数错误")
    if not payload.group_id.isdigit() or not payload.user_id.isdigit():
        json_error(400, "参数错误：group_id 和 user_id 必须为数字")
    _cid, _ckey, _server, expire, salt = geetest_config(db)
    token = generate_token(payload.group_id, payload.user_id, salt)
    ts = now_ts()
    db.add(
        VerifyTicket(
            token=token,
            api_key_id=auth.api_key_id,
            group_id=payload.group_id,
            user_id=payload.user_id,
            verified=False,
            used=False,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            expire_at=ts + expire,
            created_at=ts,
            updated_at=ts,
        )
    )
    db.commit()
    url = str(request.base_url).rstrip("/") + f"/v/{token}"
    return {"code": 0, "msg": "success", "data": {"ticket": token, "url": url, "expire": expire}}


@app.get(
    "/verify/status/{ticket}",
    response_model=VerifyStatusResponse,
    summary="查询 ticket 状态",
    description="前端轮询 ticket 当前状态；未验证时返回 captcha_id，已验证时返回验证码。",
)
async def verify_status(ticket: str, db: Annotated[Session, Depends(get_db)], request: Request):
    request.state.ticket = ticket
    if not ticket:
        json_error(400, "参数错误")
    captcha_id, _key, _server, expire, _salt = geetest_config(db)
    row = db.query(VerifyTicket).filter(VerifyTicket.token == ticket).first()
    if row is None or row.expire_at < now_ts():
        json_error(404, "验证链接已过期或不存在")
    assert row is not None
    data = {
        "ticket": ticket,
        "verified": bool(row.verified),
        "code_expire": expire,
        "expire_minutes": ceil(expire / 60),
    }
    if row.verified:
        data["code"] = row.code
    else:
        data["captcha_id"] = captcha_id
    return {"code": 0, "msg": "success", "data": data}


@app.post(
    "/verify/callback",
    response_model=VerifyCallbackResponse,
    summary="极验回调",
    description=(
        "前端提交 Geetest V4 验证结果，服务端向极验校验后生成 6 位验证码。支持 JSON 或表单提交。"
    ),
)
async def verify_callback(request: Request, db: Annotated[Session, Depends(get_db)]):
    raw = await get_payload(request)
    ticket = str(raw.get("ticket", ""))
    request.state.ticket = ticket
    limit_key = f"ticket:{ticket}" if ticket else f"ip:{client_ip(request) or 'unknown'}"
    retry = rate_limit_hit(f"rl:verify_callback:{limit_key}", 30, 60)
    if retry:
        raise retry_response(retry)
    payload = VerifyCallbackRequest.model_validate(raw)
    missing = [k for k, v in payload.model_dump().items() if not str(v or "")]
    if "ticket" in missing:
        json_error(400, "参数错误")
    if missing:
        json_error(400, "参数错误：缺少验证必填参数")
    row = db.query(VerifyTicket).filter(VerifyTicket.token == payload.ticket).first()
    if row is None or row.expire_at < now_ts():
        json_error(404, "验证链接已过期或不存在")
    assert row is not None
    if row.verified:
        return {"code": 0, "msg": "已验证"}
    ok = await verify_geetest(db, payload.model_dump())
    if not ok:
        json_error(400, "验证失败，请重试")
    for _ in range(10):
        code = generate_code()
        exists = (
            db.query(VerifyTicket)
            .filter(
                VerifyTicket.code == code,
                VerifyTicket.group_id == row.group_id,
                VerifyTicket.verified.is_(True),
                VerifyTicket.used.is_(False),
                VerifyTicket.expire_at > now_ts(),
            )
            .first()
        )
        if exists is None:
            break
    else:
        json_error(500, "验证码生成失败：连续碰撞次数过多，请稍后重试")
    row.verified = True
    row.code = code
    row.verified_at = now_ts()
    row.updated_at = now_ts()
    request.state.code = code
    db.commit()
    return {"code": 0, "msg": "验证成功", "data": {"code": code}}


@app.post(
    "/verify/check",
    response_model=VerifyCheckResponse,
    summary="校验验证码",
    description=(
        "机器人使用 API Key 校验用户提交的 6 位验证码；校验成功后验证码立即标记为已使用。"
        "支持 JSON 或表单提交。"
    ),
)
async def verify_check(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[AuthContext, Depends(current_auth)],
):
    retry = rate_limit_hit(f"rl:verify_check:{client_ip(request) or 'unknown'}", 60, 60)
    if retry:
        raise retry_response(retry, passed=False)
    payload = VerifyCheckRequest.model_validate(await get_payload(request))
    request.state.group_id = payload.group_id
    request.state.user_id = payload.user_id
    request.state.code = payload.code
    if not payload.group_id or not payload.code:
        json_error(400, "参数错误：缺少必填参数 group_id 或 code", passed=False)
    retry_group = rate_limit_hit(f"rl:verify_check:group:{payload.group_id}", 30, 60)
    if retry_group:
        raise retry_response(retry_group, passed=False)
    if not payload.group_id.isdigit():
        json_error(400, "参数错误：group_id 必须为数字", passed=False)
    if payload.user_id and not payload.user_id.isdigit():
        json_error(400, "参数错误：user_id 必须为数字", passed=False)
    now = now_ts()
    row = (
        db.query(VerifyTicket)
        .filter(
            VerifyTicket.code == payload.code,
            VerifyTicket.group_id == payload.group_id,
            VerifyTicket.verified.is_(True),
            VerifyTicket.used.is_(False),
            VerifyTicket.expire_at > now,
        )
        .first()
    )
    if row is None:
        old = (
            db.query(VerifyTicket)
            .filter(
                VerifyTicket.code == payload.code,
                VerifyTicket.group_id == payload.group_id,
                VerifyTicket.verified.is_(True),
            )
            .first()
        )
        if old and old.used:
            json_error(400, "验证失败：验证码已使用", passed=False)
        if old and old.expire_at < now:
            json_error(400, "验证失败：验证码已过期", passed=False)
        if old and not old.verified:
            json_error(400, "验证失败：验证码未完成验证", passed=False)
        json_error(400, "验证失败：验证码不存在或已失效", passed=False)
    assert row is not None
    if payload.user_id and row.user_id != payload.user_id:
        json_error(400, "验证失败：用户ID不匹配", passed=False)
    updated = (
        db.query(VerifyTicket)
        .filter(VerifyTicket.id == row.id, VerifyTicket.used.is_(False))
        .update({"used": True, "used_at": now, "updated_at": now})
    )
    if updated <= 0:
        json_error(400, "验证失败：验证码已使用", passed=False)
    db.commit()
    return {
        "code": 0,
        "msg": "验证通过",
        "passed": True,
        "data": {"user_id": row.user_id, "group_id": row.group_id},
    }


@app.get(
    "/verify/clean",
    response_model=ApiResponse,
    summary="清理过期验证码",
    description="默认 API Key 调用，删除已过期的 ticket 与验证码记录。",
)
@app.post(
    "/verify/clean",
    response_model=ApiResponse,
    summary="清理过期验证码",
    description="默认 API Key 调用，删除已过期的 ticket 与验证码记录。",
)
async def verify_clean(
    db: Annotated[Session, Depends(get_db)], auth: Annotated[AuthContext, Depends(current_auth)]
):
    require_default(auth)
    deleted = db.query(VerifyTicket).filter(VerifyTicket.expire_at < now_ts()).delete()
    db.commit()
    return {"code": 0, "msg": f"清理了 {deleted} 个过期验证码"}


@app.post(
    "/verify/reset-key",
    response_model=ApiResponse,
    summary="重置当前 API Key",
    description="仅默认 API Key 可调用，重置当前默认 key 并返回新 key 明文。",
)
async def verify_reset_key(
    db: Annotated[Session, Depends(get_db)], auth: Annotated[AuthContext, Depends(current_auth)]
):
    require_default(auth)
    retry = rate_limit_hit(f"rl:api_key_reset:{auth.api_key_id}", 3, 60)
    if retry:
        raise retry_response(retry)
    value = secrets.token_hex(32)
    row = db.get(ApiKey, auth.api_key_id)
    if row is None:
        json_error(500, "重置失败")
    assert row is not None
    row.hash = sha256_hex(value)
    row.updated_at = now_ts()
    db.commit()
    return JSONResponse(
        {
            "code": 0,
            "msg": "success",
            "data": {"id": row.id, "value": value, "updated_at": row.updated_at},
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get(
    "/admin/dashboard",
    response_model=ApiResponse,
    summary="仪表盘概览",
    description="返回 API Key、ticket 与最近 24 小时调用统计。",
)
async def admin_dashboard(
    db: Annotated[Session, Depends(get_db)], auth: Annotated[AuthContext, Depends(current_auth)]
):
    require_default(auth)
    now = now_ts()
    from24h = now - 86400
    calls_by_endpoint = [
        {"endpoint": endpoint, "count": count}
        for endpoint, count in db.query(ApiCallLog.endpoint, func.count(ApiCallLog.id))
        .filter(ApiCallLog.created_at >= from24h)
        .group_by(ApiCallLog.endpoint)
        .order_by(func.count(ApiCallLog.id).desc())
        .limit(10)
    ]
    top_groups = [
        {"group_id": group_id, "count": count}
        for group_id, count in db.query(ApiCallLog.group_id, func.count(ApiCallLog.id))
        .filter(ApiCallLog.created_at >= from24h, ApiCallLog.group_id != None)  # noqa: E711
        .group_by(ApiCallLog.group_id)
        .order_by(func.count(ApiCallLog.id).desc())
        .limit(10)
    ]
    recent = db.query(ApiCallLog).order_by(ApiCallLog.id.desc()).limit(20).all()
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "now": now,
            "api_keys_total": count_rows(db, ApiKey),
            "tickets_total": count_rows(db, VerifyTicket),
            "tickets_verified_total": count_rows(db, VerifyTicket, VerifyTicket.verified.is_(True)),
            "tickets_used_total": count_rows(db, VerifyTicket, VerifyTicket.used.is_(True)),
            "tickets_pending": count_rows(
                db, VerifyTicket, VerifyTicket.verified.is_(False), VerifyTicket.expire_at > now
            ),
            "tickets_expired_total": count_rows(db, VerifyTicket, VerifyTicket.expire_at <= now),
            "calls_24h_total": count_rows(db, ApiCallLog, ApiCallLog.created_at >= from24h),
            "calls_24h_error": count_rows(
                db, ApiCallLog, ApiCallLog.created_at >= from24h, ApiCallLog.status_code >= 400
            ),
            "calls_24h_by_endpoint": calls_by_endpoint,
            "calls_24h_top_groups": top_groups,
            "recent_calls": [log_to_dict(x) for x in recent],
        },
    }


@app.get(
    "/admin/api-call-logs",
    response_model=ApiResponse,
    summary="查询 API 调用日志",
    description="按分页、时间、状态码、endpoint、群号或用户过滤调用日志。",
)
async def admin_api_call_logs(
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(current_auth)],
    page: int = 1,
    page_size: int = 20,
    from_: Annotated[int, Query(alias="from")] = 0,
    to: int = 0,
    api_key_id: int = 0,
    status_code: int = 0,
    endpoint: str = "",
    group_id: str = "",
    user_id: str = "",
):
    require_default(auth)
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    q = db.query(ApiCallLog)
    if from_ > 0:
        q = q.filter(ApiCallLog.created_at >= from_)
    if to > 0:
        q = q.filter(ApiCallLog.created_at <= to)
    if api_key_id > 0:
        q = q.filter(ApiCallLog.api_key_id == api_key_id)
    if status_code > 0:
        q = q.filter(ApiCallLog.status_code == status_code)
    if endpoint:
        q = q.filter(ApiCallLog.endpoint.contains(endpoint))
    if group_id:
        q = q.filter(ApiCallLog.group_id == group_id)
    if user_id:
        q = q.filter(ApiCallLog.user_id == user_id)
    total = q.count()
    rows = q.order_by(ApiCallLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "items": [log_to_dict(x) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


def log_to_dict(row: ApiCallLog) -> dict[str, Any]:
    return {
        k: getattr(row, k)
        for k in [
            "id",
            "created_at",
            "api_key_id",
            "endpoint",
            "method",
            "status_code",
            "group_id",
            "user_id",
            "ticket",
            "code",
            "ip",
            "user_agent",
            "duration_ms",
        ]
    }


SETTINGS_DEFS = {
    "GEETEST_CAPTCHA_ID": (False, "string"),
    "GEETEST_CAPTCHA_KEY": (True, "string"),
    "GEETEST_API_SERVER": (False, "url"),
    "GEETEST_CODE_EXPIRE": (False, "int"),
    "API_KEY": (True, "string"),
    "SALT": (True, "string"),
}


@app.get(
    "/admin/settings",
    response_model=ApiResponse,
    summary="获取配置项",
    description="返回可管理配置项；敏感字段仅返回 masked。",
)
async def admin_settings_get(
    db: Annotated[Session, Depends(get_db)], auth: Annotated[AuthContext, Depends(current_auth)]
):
    require_default(auth)
    items = []
    for key, (secret, _type) in SETTINGS_DEFS.items():
        if key == "API_KEY":
            count = db.query(ApiKey).count()
            items.append(
                {
                    "key": key,
                    "label": key,
                    "is_set": count > 0,
                    "value": "",
                    "masked": f"{count} 个密钥已配置" if count else "",
                    "source": "API_KEYS",
                }
            )
            continue
        default = {
            "GEETEST_CAPTCHA_ID": settings.geetest.captcha_id,
            "GEETEST_CAPTCHA_KEY": settings.geetest.captcha_key,
            "GEETEST_API_SERVER": settings.geetest.api_server,
            "GEETEST_CODE_EXPIRE": str(settings.geetest.code_expire),
            "SALT": settings.salt,
        }.get(key, "")
        row = db.query(Setting).filter(Setting.name == key).first()
        value = row.value if row else default
        items.append(
            {
                "key": key,
                "label": key,
                "is_set": bool(value),
                "value": "" if secret else value,
                "masked": mask_secret(value) if secret and value else "",
                "source": "DB" if row else "ENV",
            }
        )
    return {"code": 0, "msg": "success", "data": {"items": items}}


@app.put(
    "/admin/settings",
    response_model=ApiResponse,
    summary="更新配置项",
    description="更新白名单内配置项；API_KEY 会替换 api_keys 表中的全部密钥。",
)
async def admin_settings_update(
    body: SettingsUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(current_auth)],
):
    require_default(auth)
    parsed = {
        k: str(v).strip() for k, v in body.values.items() if k in SETTINGS_DEFS and str(v).strip()
    }
    errors: list[str] = []
    for key, value in parsed.items():
        if key == "GEETEST_CODE_EXPIRE" and (not value.isdigit() or not 30 <= int(value) <= 3600):
            errors.append(f"{key} 建议在 30~3600 之间")
        if key == "GEETEST_API_SERVER" and not value.startswith(("http://", "https://")):
            errors.append(f"{key} 不是合法 URL")
        if key == "SALT" and len(value) < 32:
            errors.append(f"{key} 建议至少 32 位")
        if key == "API_KEY" and any(len(k) < 16 for k in normalize_api_keys(value)):
            errors.append(f"{key} 每个密钥建议至少 16 位")
    if errors:
        json_error(400, "；".join(errors))
    ts = now_ts()
    for key, value in parsed.items():
        if key == "API_KEY":
            db.query(ApiKey).delete()
            db.add_all(
                [
                    ApiKey(hash=sha256_hex(k), created_at=ts, updated_at=ts)
                    for k in normalize_api_keys(value)
                ]
            )
        else:
            upsert_setting(db, key, value)
    db.commit()
    return await admin_settings_get(db, auth)


@app.get(
    "/admin/api-keys",
    response_model=ApiResponse,
    summary="列出 API Keys",
    description="返回 API Key 列表，可通过 id 查询指定 key。",
)
async def admin_api_keys_list(
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(current_auth)],
    id: str = "",
):
    require_default(auth)
    if id and not id.isdigit():
        json_error(400, "参数错误")
    q = db.query(ApiKey)
    if id:
        q = q.filter(ApiKey.id == int(id))
    default_id = default_api_key_id(db)
    items = [
        {
            "id": row.id,
            "is_default": row.id == default_id,
            "masked": f"Key#{row.id} ({row.hash[:4]}...{row.hash[-4:]})",
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in q.order_by(ApiKey.id.desc()).all()
    ]
    return {"code": 0, "msg": "success", "data": {"items": items}}


@app.post(
    "/admin/api-keys",
    response_model=ApiResponse,
    summary="创建 API Key",
    description="创建一个 API Key；未传 value 时自动生成，响应仅本次返回明文。",
)
async def admin_api_keys_create(
    body: ApiKeyCreateRequest | None,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(current_auth)],
):
    require_default(auth)
    value = ((body.value if body else None) or secrets.token_hex(32)).strip()
    if len(value) < 16:
        json_error(400, "密钥长度至少 16 位")
    h = sha256_hex(value)
    if db.query(ApiKey).filter(ApiKey.hash == h).first():
        json_error(409, "密钥已存在")
    ts = now_ts()
    row = ApiKey(hash=h, created_at=ts, updated_at=ts)
    db.add(row)
    db.commit()
    return JSONResponse(
        {
            "code": 0,
            "msg": "success",
            "data": {
                "id": row.id,
                "value": value,
                "masked": mask_secret(value),
                "created_at": ts,
                "updated_at": ts,
            },
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post(
    "/admin/api-keys/{id}/reset",
    response_model=ApiResponse,
    summary="重置 API Key",
    description="重置指定 API Key 并返回新 key 明文。",
)
async def admin_api_keys_reset(
    id: str,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(current_auth)],
):
    require_default(auth)
    if not id.isdigit():
        json_error(400, "参数错误")
    row = db.get(ApiKey, int(id))
    if row is None:
        json_error(500, "重置失败")
    assert row is not None
    value = secrets.token_hex(32)
    row.hash = sha256_hex(value)
    row.updated_at = now_ts()
    db.commit()
    return JSONResponse(
        {
            "code": 0,
            "msg": "success",
            "data": {
                "id": row.id,
                "value": value,
                "masked": mask_secret(value),
                "updated_at": row.updated_at,
            },
        },
        headers={"Cache-Control": "no-store"},
    )


@app.delete(
    "/admin/api-keys/{id}",
    response_model=ApiResponse,
    summary="删除 API Key",
    description="删除指定 API Key；默认 key 不可删除。",
)
async def admin_api_keys_delete(
    id: str,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(current_auth)],
):
    require_default(auth)
    if not id.isdigit():
        json_error(400, "参数错误")
    target = int(id)
    if target == default_api_key_id(db):
        json_error(403, "当前使用的 API Key 不可删除")
    row = db.get(ApiKey, target)
    if row is None:
        json_error(404, "不存在")
    assert row is not None
    db.delete(row)
    db.commit()
    return {"code": 0, "msg": "success", "data": {"deleted": 1}}


def verify_index() -> Path:
    return BASE_DIR / "public" / "static" / "verify" / "index.html"


@app.get(
    "/v/{ticket}",
    response_class=HTMLResponse,
    summary="打开验证页面",
    description="返回前端验证页 HTML。",
)
async def verify_page(ticket: str):
    if not ticket:
        return Response("无效的验证链接", status_code=400)
    html = verify_index()
    if not html.exists():
        return Response("验证页面资源缺失", status_code=500)
    return FileResponse(html, media_type="text/html")


@app.get(
    "/admin",
    response_class=HTMLResponse,
    summary="管理后台页面",
    description="返回管理后台前端页面。",
)
@app.get(
    "/admin/login",
    response_class=HTMLResponse,
    summary="管理后台登录页",
    description="返回管理后台登录页面。",
)
async def admin_page():
    html = verify_index()
    if not html.exists():
        return Response("验证页面资源缺失", status_code=500)
    return FileResponse(html, media_type="text/html")


static_dir = BASE_DIR / "public" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return Response("", status_code=403)


def run() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
