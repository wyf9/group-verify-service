from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent


def deep_merge_dict(base: dict[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in new.items():
        if isinstance(result.get(key), dict) and isinstance(value, Mapping):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result


class GeetestConfig(BaseModel):
    captcha_id: str = ""
    captcha_key: str = ""
    api_server: str = "https://gcaptcha4.geetest.com"
    code_expire: int = 300


class AppConfig(BaseModel):
    api_key: str | list[str] = ""
    salt: str = ""
    geetest: GeetestConfig = Field(default_factory=GeetestConfig)
    database: str = "sqlite:///./data.db"
    log_level: str = "INFO"
    enable_doc: bool = True


def _parse_scalar(value: str) -> Any:
    v = value.strip()
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    if v.lower() in {"null", "none"}:
        return None
    if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
        return int(v)
    if (v.startswith("[") and v.endswith("]")) or (v.startswith("{") and v.endswith("}")):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return value
    return value


ENV_MAP = {
    "API_KEY": ("api_key",),
    "SALT": ("salt",),
    "GEETEST_CAPTCHA_ID": ("geetest", "captcha_id"),
    "GEETEST_CAPTCHA_KEY": ("geetest", "captcha_key"),
    "GEETEST_API_SERVER": ("geetest", "api_server"),
    "GEETEST_CODE_EXPIRE": ("geetest", "code_expire"),
    "DATABASE": ("database",),
    "DATABASE_URL": ("database",),
    "DB_URL": ("database",),
    "DB_PATH": ("database",),
    "LOG_LEVEL": ("log_level",),
    "ENABLE_DOC": ("enable_doc",),
}


def _env_to_nested(values: Mapping[str, str | None]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for env_key, path in ENV_MAP.items():
        raw = values.get(env_key)
        if raw is None or str(raw).strip() == "":
            continue
        value = _parse_scalar(str(raw))
        if env_key == "DB_PATH" and not str(value).startswith(("sqlite://", "mysql", "postgresql")):
            value = f"sqlite:///{value}"
        cur = data
        for part in path[:-1]:
            cur = cur.setdefault(part, {})
        cur[path[-1]] = value
    return data


def load_config() -> AppConfig:
    config_path = BASE_DIR / "config.yaml"
    raw: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    env_file = _env_to_nested(dotenv_values(BASE_DIR / ".env"))
    env_vars = _env_to_nested(os.environ)
    merged = deep_merge_dict(deep_merge_dict(raw, env_file), env_vars)
    return AppConfig.model_validate(merged)


settings = load_config()
