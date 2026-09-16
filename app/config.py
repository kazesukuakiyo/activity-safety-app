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


class Settings:
    secret_key: str = os.environ.get("APP_SECRET_KEY", "dev-secret-key-change-me")
    auth_mode: str = os.environ.get("AUTH_MODE", "dev")
    database_url: str = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'app.db'}")
    data_dir: Path = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).resolve()
    staff_notify_email: str = os.environ.get("STAFF_NOTIFY_EMAIL", "staff@example.ac.jp")

    # Entra ID (後で実装)
    entra_tenant_id: str = os.environ.get("ENTRA_TENANT_ID", "")
    entra_client_id: str = os.environ.get("ENTRA_CLIENT_ID", "")
    entra_client_secret: str = os.environ.get("ENTRA_CLIENT_SECRET", "")
    entra_redirect_uri: str = os.environ.get("ENTRA_REDIRECT_URI", "http://localhost:8000/auth/callback")

    @property
    def activity_docs_dir(self) -> Path:
        """行程表・大会要項など「活動資料」の保管先 (課外活動申請サイト相当)。"""
        return self.data_dir / "activity_docs"


settings = Settings()
