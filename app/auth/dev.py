"""ローカル検証用の疑似ログイン。

一覧から利用者を選ぶだけでログインできる。本番では使わない (AUTH_MODE=entra)。
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from .base import Role, User, login_user, logout_user

# 疑似ユーザー一覧。seed.py の団体台帳と対応している。
DEV_USERS: list[User] = [
    User(email="tanaka@example.ac.jp", name="田中 太郎 (テニス部 代表)", role=Role.STUDENT),
    User(email="suzuki@example.ac.jp", name="鈴木 花子 (登山部 副代表)", role=Role.STUDENT),
    User(email="sato@example.ac.jp", name="佐藤 次郎 (どの団体の代表でもない学生)", role=Role.STUDENT),
    User(email="advisor.tennis@example.ac.jp", name="山本 教授 (テニス部 顧問)", role=Role.ADVISOR),
    User(email="staff@example.ac.jp", name="高橋 (学生支援課 指定職員)", role=Role.STAFF),
    User(email="manager@example.ac.jp", name="伊藤 (学生支援課長)", role=Role.MANAGER),
    User(email="sysadmin@example.ac.jp", name="渡辺 (システム保守)", role=Role.SYSADMIN),
]

router = APIRouter(prefix="/auth", tags=["auth"])


def find_dev_user(email: str) -> User | None:
    return next((u for u in DEV_USERS if u.email == email), None)


@router.get("/login")
def login_page(request: Request):
    from ..main import templates

    return templates.TemplateResponse(request, "login.html", {"users": DEV_USERS, "next": request.query_params.get("next", "/")})


@router.post("/login")
def login_submit(request: Request, email: str = Form(...), next: str = Form("/")):
    user = find_dev_user(email)
    if user is None:
        return RedirectResponse("/auth/login", status_code=303)
    login_user(request, user)
    if not next.startswith("/"):
        next = "/"
    return RedirectResponse(next, status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/auth/login", status_code=303)
