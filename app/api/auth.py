"""
认证 API — GitHub OAuth 登录回调 + 当前用户信息。
"""
import secrets
import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core.security import create_access_token
from app.core.db import get_db_connection
from app.core.auth_middleware import get_current_user
from app.core.rate_limiter import limiter
from app.core.logger import logger

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_redirect_uri(request: Request) -> str:
    """根据实际请求的 Host 动态生成回调地址，避免 localhost/127.0.0.1 域名不一致。

    - 优先使用请求的 host（与浏览器访问域名一致，cookie 才能对上）。
    - 若配置了 github_redirect_uri 且是完整地址，则保留配置（用于生产/公网域名）。
    """
    configured = (settings.github_redirect_uri or "").strip()
    # 配置的地址不带域名部分（如 "/api/auth/github/callback"）或为空时，用请求 host 拼接
    if not configured.startswith("http"):
        scheme = request.url.scheme
        host = request.headers.get("host", "")
        base = configured if configured.startswith("/") else "/api/auth/github/callback"
        return f"{scheme}://{host}{base}"
    return configured


@router.get("/github/login")
@limiter.limit("10/minute")
async def github_login(request: Request):
    """重定向到 GitHub 授权页。"""
    state = secrets.token_urlsafe(32)
    redirect_uri = _build_redirect_uri(request)
    # prompt 行为可配置：默认 select_account（允许切号），
    # 可在 settings 中配置（如空字符串）以恢复单账号静默登录
    prompt = settings.github_oauth_prompt
    prompt_q = f"&prompt={prompt}" if prompt else ""
    redirect_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user:email"
        f"&state={state}"
        f"{prompt_q}"
    )
    response = RedirectResponse(url=redirect_url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        max_age=600,
        samesite="lax",
        secure=False,
    )
    return response


@router.get("/github/callback")
@limiter.limit("10/minute")
async def github_callback(code: str, state: str, request: Request):
    """GitHub OAuth 回调：验证 state → 换 token → 查用户 → 签发 JWT。"""
    saved_state = request.cookies.get("oauth_state", "")
    if state != saved_state:
        raise HTTPException(status_code=403, detail="CSRF 验证失败")

    async with httpx.AsyncClient() as client:
        # 用 code 换 access_token
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_resp.json()
        gh_access_token = token_data.get("access_token")
        if not gh_access_token:
            logger.error("GitHub OAuth 换 token 失败 — {}", token_data)
            raise HTTPException(status_code=400, detail="GitHub 授权失败")

        # 查用户信息
        gh_headers = {"Authorization": f"Bearer {gh_access_token}"}
        user_resp = await client.get("https://api.github.com/user", headers=gh_headers)
        user_data = user_resp.json()

        # 查邮箱
        email_resp = await client.get("https://api.github.com/user/emails", headers=gh_headers)
        emails = email_resp.json()
        primary_email = next((e["email"] for e in emails if e.get("primary")), None)

    # 创建或更新用户（不存 access_token，用完即弃）
    github_id = user_data["id"]
    username = user_data["login"]
    avatar_url = user_data.get("avatar_url")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE github_id = %s", (github_id,))
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    "UPDATE users SET username=%s, email=%s, avatar_url=%s, "
                    "last_login_at=NOW() WHERE github_id=%s",
                    (username, primary_email, avatar_url, github_id),
                )
                user_id = existing["id"]
                logger.info("用户登录 — github_id: {}, username: {}", github_id, username)
            else:
                cursor.execute(
                    "INSERT INTO users (username, email, github_id, avatar_url) "
                    "VALUES (%s,%s,%s,%s)",
                    (username, primary_email, github_id, avatar_url),
                )
                user_id = cursor.lastrowid
                logger.info("新用户注册 — github_id: {}, username: {}", github_id, username)
        conn.commit()
    finally:
        conn.close()

    jwt_token = create_access_token(user_id, username=username)
    # 登录成功后跳转前端根路径，由前端 handleOAuthCallback 消费 ?token=
    # SPA 由 FastAPI serve frontend/dist 在根路径
    response = RedirectResponse(url=f"/?token={jwt_token}")
    response.delete_cookie("oauth_state")
    return response


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """返回当前登录用户信息（需要 JWT）。"""
    return current_user
