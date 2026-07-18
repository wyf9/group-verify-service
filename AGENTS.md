# AGENTS.md

## Project Overview

- `backend-py/` is the recommended backend. It is a Python 3.13+ FastAPI service that serves both API routes and the built frontend static files.
- `backend-php/` is the legacy ThinkPHP backend kept for compatibility/reference.
- `frontend/` is the Vue/Vite frontend. Use Bun for package management. Its production build output is `backend-py/public/static/verify/`.
- `API.md` is the compatibility contract. Backend API behavior should remain compatible with it unless the API document is intentionally updated.

## Backend Python Tooling

- Package manager: `uv`.
- Python version: `backend-py/.python-version` pins `3.13` for uv-managed environments.
- Web framework: FastAPI.
- Database layer: SQLAlchemy. Default database URL is `sqlite:///./data.db`.
- Formatter/linter: `ruff`.
- Type checker: `ty`.

Recommended verification from `backend-py/`:

```bash
uv sync
uv run ruff format .
uv run ruff check .
uv run ty check .
```

## Frontend Tooling

- Package manager/runtime: `bun`.
- Common commands from `frontend/`: `bun install`, `bun run dev`, `bun run build`, `bun run lint`.

## Git Hooks

- Hook manager: `prek` using the native `prek.toml` format.
- Run all configured hooks with `prek run --all-files`.
- Install hooks with `prek install`.

## Configuration

- Python backend config sources are merged in this priority order: environment variables > `.env` > `config.yaml`.
- Supported core config keys include `api_key`, `salt`, `geetest`, `database`, `log_level`, and `enable_doc`.
- Keep secrets such as `API_KEY`, `SALT`, and `GEETEST_CAPTCHA_KEY` out of git.

## Constraints

- Preserve API compatibility with `API.md` when changing route behavior, status codes, or response shapes.
- Add readable FastAPI route metadata and request/response models for new routes so Swagger remains useful.
- Do not modify generated frontend build artifacts unless intentionally rebuilding or copying the static frontend.
- Do not revert unrelated user changes in the working tree.
