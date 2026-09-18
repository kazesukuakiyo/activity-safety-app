"""Azure App Service の認証ヘッダーから利用者と役割を決める処理のテスト"""

from __future__ import annotations

import base64
import json

from app.auth import easyauth
from app.config import settings


def _principal(name: str) -> str:
    return base64.b64encode(json.dumps({"claims": [{"typ": "name", "val": name}]}).encode()).decode()


def test_roles_from_headers(app_env, monkeypatch):
    monkeypatch.setattr(settings, "staff_emails", frozenset({"staff@example.ac.jp"}))
    monkeypatch.setattr(settings, "manager_emails", frozenset({"kacho@example.ac.jp"}))
    monkeypatch.setattr(settings, "sysadmin_emails", frozenset({"sysadmin@example.ac.jp"}))

    def user(email, name=None):
        h = {"x-ms-client-principal-name": email}
        if name:
            h["x-ms-client-principal"] = _principal(name)
        return easyauth.user_from_headers(h)

    assert user("Staff@Example.ac.jp", "高橋").role.value == "staff"
    assert user("kacho@example.ac.jp").role.value == "manager"
    assert user("sysadmin@example.ac.jp").role.value == "sysadmin"
    assert user("advisor.tennis@example.ac.jp", "山本").role.value == "advisor"  # 団体台帳の顧問メール
    u = user("tanaka@example.ac.jp", "田中 太郎")
    assert u.role.value == "student" and u.name == "田中 太郎" and u.email == "tanaka@example.ac.jp"
    assert user("someone@example.ac.jp").name == "someone@example.ac.jp"  # 氏名が取れなければメール
    assert easyauth.user_from_headers({}) is None  # 未ログイン
