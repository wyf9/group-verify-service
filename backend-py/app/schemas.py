from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = Field(description="业务状态码，0 表示成功")
    msg: str = Field(description="响应消息")
    data: Any | None = Field(default=None, description="响应数据")


class VerifyCreateRequest(BaseModel):
    group_id: str = Field(description="群/分组 ID，必须为纯数字字符串")
    user_id: str = Field(description="用户 ID，必须为纯数字字符串")


class VerifyCreateData(BaseModel):
    ticket: str
    url: str
    expire: int


class VerifyCreateResponse(ApiResponse):
    data: VerifyCreateData


class VerifyStatusData(BaseModel):
    ticket: str
    verified: bool
    captcha_id: str | None = None
    code: str | None = None
    code_expire: int
    expire_minutes: int


class VerifyStatusResponse(ApiResponse):
    data: VerifyStatusData


class VerifyCallbackRequest(BaseModel):
    ticket: str
    lot_number: str
    captcha_output: str
    pass_token: str
    gen_time: str


class VerifyCallbackData(BaseModel):
    code: str


class VerifyCallbackResponse(ApiResponse):
    data: VerifyCallbackData | None = None


class VerifyCheckRequest(BaseModel):
    group_id: str
    user_id: str | None = ""
    code: str


class VerifyCheckData(BaseModel):
    user_id: str
    group_id: str


class VerifyCheckResponse(ApiResponse):
    passed: bool
    data: VerifyCheckData | None = None


class ApiKeyCreateRequest(BaseModel):
    value: str | None = Field(default=None, description="自定义密钥，不传则自动生成")


class ApiKeyItem(BaseModel):
    id: int
    is_default: bool | None = None
    masked: str
    created_at: int | None = None
    updated_at: int | None = None


class SettingsUpdateRequest(BaseModel):
    values: dict[str, Any]


class ApiCallLogItem(BaseModel):
    id: int
    created_at: int
    api_key_id: int | None = None
    endpoint: str
    method: str
    status_code: int
    group_id: str | None = None
    user_id: str | None = None
    ticket: str | None = None
    code: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    duration_ms: int
