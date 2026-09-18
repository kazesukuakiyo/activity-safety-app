"""設定値。環境変数または .env ファイルから読み込む。"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """外部ライブラリなしで .env を読む (KEY=VALUE 形式のみ)。"""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split("#", 1)[0].strip()
        os.environ.setdefault(key.strip(), value)


_load_dotenv()


def _emails(name: str) -> frozenset[str]:
    """カンマ区切りのメール一覧を小文字の集合にする"""
    return frozenset(e.strip().lower() for e in os.environ.get(name, "").split(",") if e.strip())


class Settings:
    secret_key: str = os.environ.get("APP_SECRET_KEY", "dev-secret-key-change-me")
    # dev      = 疑似ログイン (ローカル検証)
    # easyauth = Azure App Service の「認証」機能 (Entra ID)。アプリは Azure が付けるヘッダーを読むだけ
    auth_mode: str = os.environ.get("AUTH_MODE", "dev")
    database_url: str = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'app.db'}")
    data_dir: Path = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).resolve()
    staff_notify_email: str = os.environ.get("STAFF_NOTIFY_EMAIL", "staff@example.ac.jp")

    # 役割の割り当て (easyauth のとき)。ここに無いメールは学生扱い。顧問は団体台帳の顧問メールで判定する
    staff_emails: frozenset[str] = _emails("STAFF_EMAILS")
    manager_emails: frozenset[str] = _emails("MANAGER_EMAILS")
    sysadmin_emails: frozenset[str] = _emails("SYSADMIN_EMAILS")

    # 起動時にマイグレーションを流すか。Azure では startup.sh が先に流すので 0 にする
    run_migrations_on_startup: bool = os.environ.get("RUN_MIGRATIONS_ON_STARTUP", "1") == "1"

    @property
    def is_dev(self) -> bool:
        return self.auth_mode == "dev"

    @property
    def session_https_only(self) -> bool:
        """本番 (dev 以外) では Cookie を HTTPS 限定にする"""
        return os.environ.get("SESSION_HTTPS_ONLY", "0" if self.is_dev else "1") == "1"

    @property
    def activity_docs_dir(self) -> Path:
        """行程表・大会要項など「活動資料」の保管先 (課外活動申請サイト相当)。"""
        return self.data_dir / "activity_docs"


settings = Settings()
