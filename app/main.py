"""課外活動安全管理システム (学外活動届) - ローカル検証用 Web アプリ"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .auth.base import user_from_session
from .config import settings
from .database import init_db

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

_WEEKDAYS = "月火水木金土日"


def _jdt(value, with_time: bool = True) -> str:
    """日本語の日時表示: 2026-10-10 (土) 08:00"""
    if value is None:
        return ""
    s = f"{value:%Y-%m-%d} ({_WEEKDAYS[value.weekday()]})"
    return f"{s} {value:%H:%M}" if with_time else s


templates.env.filters["jdt"] = _jdt


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()
    settings.activity_docs_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="課外活動安全管理システム (学外活動届)", docs_url=None, redoc_url=None, lifespan=_lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


# 認証方式の切替 (dev: 疑似ログイン / entra: Entra ID)
if settings.auth_mode == "entra":
    from .auth import entra as auth_module
else:
    from .auth import dev as auth_module
app.include_router(auth_module.router)

from .routers import dashboard, notifications, orgs, reports, rosters  # noqa: E402

app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(orgs.router)
app.include_router(rosters.router)
app.include_router(notifications.router)


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401:
        return RedirectResponse(f"/auth/login?next={request.url.path}", status_code=303)
    user = user_from_session(request)
    return templates.TemplateResponse(
        request,
        "error.html",
        {"user": user, "status_code": exc.status_code, "detail": exc.detail},
        status_code=exc.status_code,
    )


@app.get("/")
def index(request: Request):
    user = user_from_session(request)
    if user is None:
        return RedirectResponse("/auth/login", status_code=303)
    if user.role.value in ("staff", "manager"):
        return RedirectResponse("/dashboard", status_code=303)
    if user.can_view_all_reports or user.role.value == "advisor":
        return RedirectResponse("/reports", status_code=303)
    return RedirectResponse("/reports/new", status_code=303)
