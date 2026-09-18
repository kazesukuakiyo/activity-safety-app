"""認証の共通部分。

ローカル検証では app/auth/dev.py の疑似ログインを使い、
本番では app/auth/entra.py (Entra ID) に差し替える。
どちらもセッションに同じ形式のユーザー情報を入れるので、画面側は変更不要。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


class Role(enum.StrEnum):
    """4. 利用者と権限"""

    STUDENT = "student"  # 学生・団体代表者: 活動届を提出できる
    ADVISOR = "advisor"  # 顧問: 通知を受ける (名簿は閲覧不可)
    STAFF = "staff"  # 指定職員: 確認・状況更新・差戻し・名簿確認
    MANAGER = "manager"  # 管理職・危機管理担当: 閲覧のみ
    SYSADMIN = "sysadmin"  # システム保守: 台帳・設定の保守 (名簿は閲覧不可)


ROLE_LABELS = {
    Role.STUDENT: "学生・団体代表者",
    Role.ADVISOR: "顧問",
    Role.STAFF: "指定職員",
    Role.MANAGER: "管理職・危機管理担当",
    Role.SYSADMIN: "システム保守担当",
}


@dataclass
class User:
    email: str
    name: str
    role: Role

    # --- 権限判定 (4. 利用者と権限) ---
    @property
    def can_submit(self) -> bool:
        return self.role == Role.STUDENT

    @property
    def can_view_all_reports(self) -> bool:
        return self.role in (Role.STAFF, Role.MANAGER, Role.SYSADMIN)

    @property
    def can_edit_reports(self) -> bool:
        return self.role == Role.STAFF

    @property
    def can_view_rosters(self) -> bool:
        """名簿保管先は指定職員・管理職に限定 (顧問・保守担当は閲覧不可)"""
        return self.role in (Role.STAFF, Role.MANAGER)

    @property
    def can_manage_orgs(self) -> bool:
        return self.role in (Role.STAFF, Role.SYSADMIN)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS[self.role]


SESSION_KEY = "user"


def user_from_session(request: Request) -> User | None:
    """ログイン中の利用者を返す (未ログインなら None)。

    認証方式によって取り出し元が変わる:
      dev      … セッション Cookie (疑似ログイン)
      easyauth … Azure App Service が付けるヘッダー (Entra ID でログイン済みの人)
    画面・業務処理はこの関数だけを見ているので、方式が変わっても他は変更不要。
    """
    from ..config import settings

    if settings.auth_mode == "easyauth":
        from . import easyauth

        return easyauth.user_from_request(request)
    data = request.session.get(SESSION_KEY)
    if not data:
        return None
    try:
        return User(email=data["email"], name=data["name"], role=Role(data["role"]))
    except (KeyError, ValueError):
        return None


def login_user(request: Request, user: User) -> None:
    request.session[SESSION_KEY] = {"email": user.email, "name": user.name, "role": user.role.value}


def logout_user(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def current_user(request: Request) -> User:
    """ログイン必須の依存関係。未ログインなら 401 (ミドルウェアでログイン画面へ誘導)。"""
    user = user_from_session(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ログインが必要です")
    return user


def forbidden(msg: str = "この操作を行う権限がありません") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
