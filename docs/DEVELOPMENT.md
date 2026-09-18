# 開発者向けメモ

このファイルは「コードをどう直すか」のためのものです。使い方は `README.md` を見てください。

## 日常の作業

```bash
source .venv/bin/activate          # 仮想環境に入る (毎回)
uvicorn app.main:app --reload      # 起動 (コードを直すと自動で再読込)
pytest -q                          # 受入テスト (約 2 秒)
ruff check . && ruff format .      # 静的チェックと整形 (push 前に必ず)
```

GitHub に push すると `.github/workflows/ci.yml` が同じことを自動で実行します。
赤くなったら、GitHub の「Actions」タブでどのステップが失敗したかを見てください。

## AI アシスタントを使うとき

GitHub Copilot (VS Code / GitHub.com) でも Claude Code でも使えます。決めごとは `AGENTS.md` に書いてあり、
Copilot は `.github/copilot-instructions.md` (同じ内容) を、Claude Code は `CLAUDE.md` 経由で自動的に読みます。
`AGENTS.md` を直したら `.github/copilot-instructions.md` にもコピーしてください。

Copilot での標準的な流れ:
1. GitHub の Issue に「何をしたいか」を日本語で書く
2. VS Code の Copilot Chat (エージェント モード) か、GitHub.com の Copilot coding agent に Issue を渡す
3. できた Pull Request で CI (テスト・静的チェック) が緑になっているのを確認し、Copilot のコードレビューも見る
4. 動作を手元で確認してマージ → Azure に自動配備

## コードの読む順番

1. `app/models.py` — テーブル定義。要件書の「活動届リスト」「団体台帳」「名簿」に対応
2. `app/services/intake.py` — 業務ルール (発番・照合・不足検査・通知・再提出)。要件書 8 章
3. `app/routers/reports.py` — 活動届の画面処理。フォーム → `_apply_form()` → `intake.process_submission()`
4. `app/auth/base.py` — 役割と権限。`User.can_*` を見れば「誰が何をできるか」が分かる
5. `tests/test_acceptance.py` — 要件書 12 章のシナリオ。仕様の実例として読める

## よくある変更のやり方

### 活動届の項目を増やす

1. `app/models.py` の `ActivityReport` に列を足す
2. `alembic revision --autogenerate -m "xxx 列を追加"` でマイグレーションを生成し、`migrations/versions/` の中身を確認
3. `app/routers/reports.py` の `_apply_form()` と `edit_form()` で読み書きする
4. `app/templates/report_form.html` と `report_detail.html` に入力欄・表示を足す
5. `tests/` に確認を足して `pytest`

### 判定ルール・通知文を変える

`app/services/intake.py` だけを直します。通知文はそこに直接書いてあります。

### 役割を増やす・権限を変える

`app/auth/base.py` の `Role` と `User.can_*`。画面側は `user.can_*` しか見ていないので、そこを直せば全画面に効きます。

### DB のテーブルを変えたとき (重要)

`data/` を消して作り直す方法は、本番でデータが入ったあとは使えません。必ず Alembic でマイグレーションを作ります。

```bash
alembic revision --autogenerate -m "変更内容"   # models.py との差分からスクリプト生成
alembic upgrade head                              # 手元の DB に適用 (アプリ起動時にも自動適用される)
alembic check                                     # models.py とマイグレーションが一致しているか (CI でも実行)
```

生成されたスクリプトは必ず目で確認してからコミットしてください。列名の変更は「削除 + 追加」として生成されるので、データを残したい場合は手で直します。

### 名簿の入力規則を変える

サーバー側は `app/services/roster.py`、画面側の即時チェックは `app/static/roster.js`。
**両方を同じ規則にしてください** (画面側は目安、最終判定はサーバー側)。

## 本番に向けて差し替える場所

| 何を | どこを | 備考 |
|---|---|---|
| 認証 (Entra ID) | `app/auth/easyauth.py` (実装済み) | `AUTH_MODE=easyauth`。役割は環境変数 `STAFF_EMAILS` 等と団体台帳の顧問メールで決まる |
| メール送信 | `app/services/notify.py` の `send()` | SMTP か Microsoft Graph |
| DB | `.env` の `DATABASE_URL` | PostgreSQL 推奨。`psycopg[binary]` は requirements に入っている |
| 添付ファイル | `app/services/storage.py` | Azure Blob Storage など |
| 秘密鍵 | `.env` の `APP_SECRET_KEY` | 本番では必ずランダムな長い文字列に |

## 決めごと

- 画面の文言は要件書 11 章の案を基本にする。専門用語・略語を避ける
- 名簿は「学籍番号・氏名・所属・学年」の 4 列以外を絶対に持たない (要件書 3.3)
- 学生・顧問・保守担当に名簿を見せない (要件書 4 章・9 章)。権限を変えるときは `tests/test_acceptance.py` の `test_8` と `test_9` を必ず通す
- 通知は `notify.send()` を経由する (ログとテストのため)
- 状況の変更は `intake.update_status()` を経由する (重複通知の抑止と監査ログのため)
