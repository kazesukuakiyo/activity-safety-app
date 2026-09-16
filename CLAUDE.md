# activity-safety-app

課外活動安全管理システム (学外活動届)。大学の部活・サークルの学外活動届を受け付け、職員が確認する Web アプリ。
FastAPI + SQLAlchemy + Jinja2 + SQLite (本番は PostgreSQL 想定)。UI・コメント・コミットメッセージは日本語。

## コマンド

- 起動: `uvicorn app.main:app --reload`
- テスト: `pytest -q` (要件書 12 章の受入シナリオ)
- 静的チェック・整形: `ruff check . && ruff format .` (push 前に必ず)
- DB 変更: `alembic revision --autogenerate -m "..."` → 生成物を確認 → `alembic check`
- 初期データ: `python seed.py`

## 構成

- `app/models.py` テーブル。`app/services/intake.py` 業務ルール (要件書 8 章)。`app/routers/` 画面処理。`app/auth/base.py` 権限
- `app/services/roster.py` と `app/static/roster.js` は同じ規則で名簿を検証する。片方を変えたら両方直す
- 詳しくは `docs/DEVELOPMENT.md`

## 守ること

- 名簿は「学籍番号・氏名・所属・学年」の 4 列以外を持たない
- 学生・顧問・システム保守担当には名簿を見せない。権限変更時は `test_8` `test_9` を通す
- テーブルを変えたら必ず Alembic のマイグレーションを作る (`data/` の削除で済ませない)
- 通知は `notify.send()`、状況変更は `intake.update_status()` を経由する
