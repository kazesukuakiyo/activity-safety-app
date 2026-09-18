# activity-safety-app — AI アシスタント・開発者向けの申し送り

課外活動安全管理システム (学外活動届)。大学の部活・サークルの学外活動届を受け付け、職員が確認する Web アプリ。
FastAPI + SQLAlchemy + Jinja2 + SQLite (本番は PostgreSQL 想定)。UI・コメント・コミットメッセージは日本語で書く。

このファイルは GitHub Copilot / Claude Code / その他の AI ツールが共通で読む。詳しい手順は `docs/DEVELOPMENT.md`。

## コマンド

- 起動: `uvicorn app.main:app --reload`
- テスト: `pytest -q` (要件書 12 章の受入シナリオ。変更後は必ず通す)
- 静的チェック・整形: `ruff check . && ruff format .` (push 前に必ず。CI でも実行される)
- DB 変更: `alembic revision --autogenerate -m "..."` → 生成物を目で確認 → `alembic check`
- 初期データ: `python seed.py`

## 構成

- `app/models.py` テーブル定義
- `app/services/intake.py` 業務ルール (発番・申請者照合・不足検査・通知・再提出。要件書 8 章)
- `app/routers/` 画面処理、`app/templates/` HTML、`app/static/` CSS/JS
- `app/auth/base.py` 役割と権限 (`User.can_*`)。`app/auth/easyauth.py` Azure の認証、`app/auth/dev.py` ローカルの疑似ログイン
- `app/services/roster.py` と `app/static/roster.js` は同じ規則で名簿を検証する。片方を変えたら両方直す
- `tests/test_acceptance.py` が仕様の実例。仕様を変えるときはテストも変える

## 守ること

- 名簿は「学籍番号・氏名・所属・学年」の 4 列以外を絶対に持たない (要件書 3.3)
- 学生・顧問・システム保守担当には名簿を見せない。権限を変えたら `test_8` `test_9` を通す
- テーブルを変えたら必ず Alembic のマイグレーションを作る (`data/` の削除で済ませない)
- 通知は `notify.send()`、状況変更は `intake.update_status()` を経由する
- 実在の学生の氏名・メールをリポジトリに入れない (テストデータは架空のもの)
- 画面の文言は平易な日本語。略語・専門用語を避ける (要件書 10 章)
