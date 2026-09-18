"""Azure App Service の「認証」機能 (Easy Auth) を使った Entra ID ログイン。

仕組み:
  Azure 側で「認証」を有効にすると、未ログインの人は Azure が自動で Entra ID のログイン画面へ送る。
  ログイン済みの人のリクエストには Azure が次のヘッダーを付けてアプリに渡す。
    X-MS-CLIENT-PRINCIPAL-NAME … メールアドレス (UPN)
    X-MS-CLIENT-PRINCIPAL      … 氏名などのクレーム (Base64 の JSON)
  アプリはそれを読むだけでよく、MSAL などのライブラリもシークレットも不要。

役割の決め方:
  - STAFF_EMAILS / MANAGER_EMAILS / SYSADMIN_EMAILS (環境変数、カンマ区切り) に載っていればその役割
  - 団体台帳のどれかの団体で顧問メールに登録されていれば 顧問
  - それ以外は 学生
"""

from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from ..config import settings
from .base import Role, User

router = APIRouter(prefix="/auth", tags=["auth"])

HEADER_NAME = "x-ms-client-principal-name"
HEADER_PRINCIPAL = "x-ms-client-principal"


def _display_name(principal_b64: str, fallback: str) -> str:
    try:
        data = json.loads(base64.b64decode(principal_b64 + "=" * (-len(principal_b64) % 4)))
    except Exception:
        return fallback
    claims = {c.get("typ"): c.get("val") for c in data.get("claims", []) if isinstance(c, dict)}
    return claims.get("name") or claims.get("preferred_username") or fallback


def _is_advisor(email: str) -> bool:
    from ..database import SessionLocal
    from ..models import Organization

    with SessionLocal() as db:
        return db.scalar(select(Organization.id).where(func.lower(Organization.advisor_email) == email)) is not None


def resolve_role(email: str) -> Role:
    email = email.lower()
    if email in settings.staff_emails:
        return Role.STAFF
    if email in settings.manager_emails:
        return Role.MANAGER
    if email in settings.sysadmin_emails:
        return Role.SYSADMIN
    if _is_advisor(email):
        return Role.ADVISOR
    return Role.STUDENT


def user_from_headers(headers) -> User | None:
    email = (headers.get(HEADER_NAME) or "").strip().lower()
    if not email:
        return None
    name = _display_name(headers.get(HEADER_PRINCIPAL, ""), email)
    return User(email=email, name=name, role=resolve_role(email))


def user_from_request(request: Request) -> User | None:
    return user_from_headers(request.headers)


@router.get("/login")
def login(request: Request):
    """Azure のログイン画面へ。通常は Azure が未ログインを自動で送るので、ここに来ることはほぼない"""
    nxt = request.query_params.get("next", "/")
    return RedirectResponse(f"/.auth/login/aad?post_login_redirect_uri={nxt}", status_code=303)


@router.post("/logout")
def logout():
    return RedirectResponse("/.auth/logout?post_logout_redirect_uri=/", status_code=303)
