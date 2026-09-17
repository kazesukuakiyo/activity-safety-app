from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import BASE_DIR, settings

# Alembic 導入時点のスキーマに対応する最初のマイグレーション (migrations/versions/ を参照)
INITIAL_REVISION = "0ecdb22b199e"


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """DB を最新のスキーマにする (Alembic のマイグレーションを head まで適用)。

    アプリ起動時と seed.py から呼ばれる。テーブル定義を変えたときは
    `alembic revision --autogenerate -m "..."` で差分スクリプトを作ってからコミットする。
    """
    from alembic import command
    from alembic.config import Config

    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))

    # Alembic 導入前 (create_all 方式) に作られた DB は、マイグレーションの記録が無いのに
    # テーブルだけ存在する。その場合は初期マイグレーション済みとして記録 (stamp) してから進める。
    names = set(inspect(engine).get_table_names())
    if "organizations" in names and "alembic_version" not in names:
        command.stamp(cfg, INITIAL_REVISION)
    command.upgrade(cfg, "head")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
