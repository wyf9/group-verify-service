# 入群极验验证后端服务 (group-verify-service)

<div align="center">

![UGC Avatar](https://socialify.git.ci/wyf9/group-verify-service/image?description=1&font=KoHo&forks=1&issues=1&language=1&name=1&owner=1&pattern=Circuit%20Board&pulls=1&stargazers=1&theme=Auto)

[![GitHub license](https://img.shields.io/github/license/wyf9/group-verify-service?style=flat-square)](https://github.com/wyf9/group-verify-service/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/wyf9/group-verify-service?style=flat-square)](https://github.com/wyf9/group-verify-service/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/wyf9/group-verify-service?style=flat-square)](https://github.com/wyf9/group-verify-service/network)
[![GitHub issues](https://img.shields.io/github/issues/wyf9/group-verify-service?style=flat-square)](https://github.com/wyf9/group-verify-service/issues)
[![python](https://img.shields.io/badge/Python-3.13+-3776AB.svg?style=flat-square)](https://www.python.org/)

</div>

## 项目简介

为项目 [astrbot_plugin_group_geetest_verify](https://github.com/VanillaNahida/astrbot_plugin_group_geetest_verify) 群聊入群验证插件开发的后端，使用极验 Geetest V4 实现入群人机验证处理。当前推荐使用 `backend-py/` FastAPI 后端，兼容原有 API，并提供验证页、管理后台、API Key、数据库持久化与调用日志等能力。

由 VanillaNahida 的项目修改而来，增加了 Python 后端，更易于部署；并进行了多项~~用处不大~~的优化（如：

- 增加 AGENTS.md
- prek pre-commit hook
- GitHub Actions 自动构建代替将构建产物直接提交到仓库

），~~至少更优雅了~~

原作:
- [VanillaNahida/group-verify-service](https://github.com/VanillaNahida/group-verify-service)
- [yjwmidc/group-verify-service](https://github.com/yjwmidc/group-verify-service/)

友链 (原项目): [Neko云](https://music.cnmsb.xin/)

## 效果展示

<div align="center">

<details>
<summary>点击展开</summary>

<img src="img/4.png" alt="效果图4" width="400" />
<br />
<img src="img/5.png" alt="效果图5" width="400" />
<br />
<img src="img/6.png" alt="效果图6" width="400" />

<details>
<summary>展开更多 (图片文件较大，注意流量)</summary>

<img src="img/1.png" alt="效果图1" width="400" />
<br />
<img src="img/2.png" alt="效果图2" width="400" />
<br />
<img src="img/3.png" alt="效果图3" width="400" />

</details>

</details>

</div>

## 主要功能

- 提供短链接验证页：`/v/:ticket`
- 集成极验 Geetest V4 行为验证
- 生成并管理一次性验证码（默认 300 秒有效）
- 提供机器人调用接口（API Key 保护）
- 提供管理后台（配置与 API Keys 管理）

## 文档

- API 文档：见 [API.md](API.md)

## 快速部署（推荐：Python + uv）

推荐优先部署 Python 后端：用 `uv` 安装依赖并运行 FastAPI。正式发布时也会提供可直接下载的 Release zip，其中已包含前端构建产物。

### Python 后端

1. 环境要求

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

如没有 uv 或较高版本的 Python，安装它：

```bash
# 其实和官方的一样，只是多了提前安装 Python 这一步 (以及替换为用加速源下载)；如果已经有了可以删去 `-s -- 3.13`
curl -fsSL sh.wss.moe/uv | bash -s -- 3.13
```

2. 下载 Release zip (`group-verify-service-python-v*.zip`) 并解压

> 也可以 Clone repo，但须自行构建前端为静态产物

3. 安装依赖并配置

```bash
cd backend-py
uv sync
cp config.example.yaml config.yaml  # 如尚未创建
```

编辑 `config.yaml` 或 `.env`，至少配置：

- `api_key` / `API_KEY`
- `salt` / `SALT`（建议至少 32 位，可用 `openssl rand -hex 32` 生成）
- `geetest.captcha_id` / `GEETEST_CAPTCHA_ID`
- `geetest.captcha_key` / `GEETEST_CAPTCHA_KEY`

4. 启动服务

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

5. 反向代理（Nginx 示例）

```nginx
location / {
  proxy_pass http://127.0.0.1:8000;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
}
```

### Release 包

Release 会提供两个 zip 包：

- `group-verify-service-python-*.zip`：推荐使用，内含 `backend-py/` 和已构建的前端静态文件
- `group-verify-service-php-*.zip`：旧版兼容包，内含 `backend-php/`、Composer 生产依赖和已构建的前端静态文件

源码仓库不再提交前端构建产物；发布包由 GitHub Actions 构建生成。打 tag（如 `v1.0.0`）会自动发布 Release，也可在 Actions 里手动运行 `Build release packages` 下载构建产物。

<details>
<summary>旧版 PHP 后端部署</summary>

PHP 后端已移动到 `backend-php/`，仅作为兼容保留。

1. 环境要求

- PHP 8.0+
- PHP 扩展：fileinfo、sqlite3、pdo_sqlite、mbstring
- Release 包已包含 Composer 生产依赖；从源码部署时才需要执行 `composer install --no-dev -o`

2. 上传并设置站点目录

- 上传 Release `group-verify-service-php-*.zip` 包内 `backend-php/` 目录全部内容
- 站点运行目录指向：`backend-php/public/`
- 确保目录可写：`backend-php/runtime/`、`backend-php/database/`

3. 配置伪静态（Nginx 示例）

```nginx
location / {
  if (!-e $request_filename) {
    rewrite ^(.*)$ /index.php?s=$1 last;
  }
}
```

4. 首次初始化

- 访问：`https://你的域名/setup`
- 按页面提示填写 `GEETEST_CAPTCHA_ID`、`GEETEST_CAPTCHA_KEY`、`API_KEY`、`SALT` 等
- 初始化成功后会生成 `.env` 并初始化 SQLite
- 仅首次可用：当 `.env` 已存在时，`/setup` 返回 `404`

</details>

## 管理后台

- 页面入口：`/admin`、`/admin/login`
- 管理接口统一使用 API Key 鉴权

## 本地开发

### 后端

```bash
cd backend-py
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

代码质量工具：

```bash
uv run ruff format .
uv run ruff check .
uv run ty check .
```

### 前端

前端源码在 `frontend/`，本地构建产物输出到 `backend-py/public/static/verify/`，该目录内容不提交到 git。Release 工作流会先构建到 Python 后端，再复制同一份静态文件到 PHP 后端包。

```bash
cd frontend
bun install
bun run dev
```

构建产物（用于部署）：

```bash
cd frontend
bun run build
```

## Release 构建

GitHub Actions 工作流位于 `.github/workflows/release.yml`，会执行：

1. 使用 Bun 安装前端依赖并构建前端
2. 将前端构建产物放入 `backend-py/public/static/verify/` 并复制到 `backend-php/public/static/verify/`
3. 校验 Python 后端：`uv sync --frozen`、`ruff format --check`、`ruff check`、`ty check`
4. 为 PHP 后端执行 `composer install --no-dev --optimize-autoloader`
5. 生成 Python / PHP 两个可部署 zip；tag 触发时自动上传到 GitHub Release

## 使用流程（机器人视角）

1. 机器人调用 `POST /verify/create` 生成验证链接（需 API Key）
2. 用户打开 `GET /v/:ticket` 完成人机验证
3. 用户将页面显示的验证码发送到群聊
4. 机器人调用 `POST /verify/check` 校验验证码（需 API Key）
5. 校验通过后验证码自动失效，不可重复使用

## 配置说明

Python 后端支持 `backend-py/config.yaml`、`backend-py/.env` 与系统环境变量，优先级为：环境变量 > `.env` > `config.yaml`。管理后台写入的运行配置会保存在数据库中。

常用配置项：

| 配置项 / 环境变量 | 说明 |
|---|---|
| `geetest.captcha_id` / `GEETEST_CAPTCHA_ID` | 极验验证码 ID |
| `geetest.captcha_key` / `GEETEST_CAPTCHA_KEY` | 极验验证码 Key |
| `geetest.api_server` / `GEETEST_API_SERVER` | 极验 API Server（默认 `https://gcaptcha4.geetest.com`） |
| `geetest.code_expire` / `GEETEST_CODE_EXPIRE` | 验证码有效期（秒，默认 300） |
| `api_key` / `API_KEY` | 首次启动写入数据库的机器人接口访问密钥（支持多个） |
| `salt` / `SALT` | ticket 生成盐值（建议至少 32 位） |
| `database` / `DATABASE` | SQLAlchemy 数据库 URL，默认 `sqlite:///./data.db` |
| `log_level` / `LOG_LEVEL` | 日志级别，默认 `INFO` |
| `enable_doc` / `ENABLE_DOC` | 是否启用 `/docs`、`/redoc`、`/openapi.json` |

## 安全建议

- 妥善保管 `GEETEST_CAPTCHA_KEY`、`API_KEY`、`SALT`，避免泄露
- 生产环境建议设置 `ENABLE_DOC=false` 关闭内置文档入口
- 建议使用 HTTPS 部署

## 许可证

Apache-2.0
