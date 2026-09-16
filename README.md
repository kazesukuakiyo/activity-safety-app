# 課外活動安全管理システム (学外活動届) — ローカル検証版

要件定義書 v3.0「Microsoft Lists Forms を入口とする最小実装」を、
**Python (FastAPI) の Web アプリ**として実装したものです。

Microsoft 365 の構成要素は次のように置き換えています。

| 要件書の構成要素 | このアプリでの実装 |
|---|---|
| Microsoft Lists Forms (学生入力画面) | `/reports/new` の Web フォーム |
| 活動届リスト (正本データ) | SQLite の `activity_reports` テーブル |
| 団体台帳 | `organizations` テーブル + `/orgs` 画面 |
| 活動資料 (行程表など) | `data/activity_docs/` フォルダ |
| 参加者名簿保管先 (個人情報管理サイト) | `data/personal_info_vault/` フォルダ (職員・管理職のみ閲覧可) |
| Power Automate (発番・照合・不足検査・通知・振分け) | `app/services/intake.py` |
| メール通知 | ローカルでは DB に記録し `/notifications` 画面で確認 |
| Entra ID 認証 | **後で実装**。今は疑似ログイン (`AUTH_MODE=dev`) |

## 動かし方 (初回)

**Python 3.11 以上**が必要です。Mac に最初から入っている Python は古いので、先に新しいものを入れてください。

- Homebrew がある場合: `brew install python@3.12`
- 無い場合: https://www.python.org/downloads/macos/ のインストーラーを実行
- 確認: `python3.12 --version` で `Python 3.12.x` と出れば OK

```bash
cd activity-safety-app

# 1. 仮想環境を作って有効化 (プロジェクト専用の Python 環境)
python3.12 -m venv .venv
source .venv/bin/activate        # Windows は: .venv\Scripts\activate
# → プロンプトの先頭に (.venv) が付く。以降の python / pip はこの環境を指す

# 2. ライブラリを入れる
pip install -r requirements.txt

# 3. 初期データ (団体台帳のサンプル) を入れる
python seed.py

# 4. 起動
uvicorn app.main:app --reload
```

2 回目以降は、ターミナルを開いたら `source .venv/bin/activate` → `uvicorn app.main:app --reload` だけで起動します。

ブラウザで http://localhost:8000 を開くと、ログイン画面が出ます。

## 検証用ユーザー (疑似ログイン)

| 利用者 | 役割 | 試せること |
|---|---|---|
| 田中 太郎 (テニス部 代表) | 学生 | 活動届の提出。申請者確認は「一致」になる |
| 鈴木 花子 (登山部 副代表) | 学生 | 副代表でも「一致」になる |
| 佐藤 次郎 (代表でない学生) | 学生 | どの団体で出しても「要確認」。軽音楽サークルは代表未登録なので「照合不可」 |
| 山本 教授 (テニス部 顧問) | 顧問 | テニス部の活動届だけ閲覧できる。名簿は見られない |
| 高橋 (指定職員) | 職員 | 全件閲覧、状況更新 (確認済/差戻し)、名簿の閲覧、団体台帳の編集 |
| 伊藤 (学生支援課長) | 管理職 | 全件閲覧と名簿閲覧のみ。編集はできない |
| 渡辺 (システム保守) | 保守 | 団体台帳の保守。名簿は見られない |

## 動作確認の流れ (受入要件 12 章に対応)

1. **田中**でログイン → 「事前確認対象 = いいえ」で提出 → 状況が「確認済」になり、通知画面に「受付完了」が出る
2. **田中**で「事前確認対象 = はい」+ 行程表・参加者名簿を添付して提出 → 「未確認」になり、職員と顧問に確認依頼が出る
3. **田中**で「はい」なのに添付なしで提出 → 自動で「差戻し」になり、不足内容の通知が出る
4. **高橋**でログイン → 一覧から開き、状況を「確認済」に変えて備考を入れる → 田中宛てに結果通知が 1 回だけ出る (同じ値で再保存しても増えない)
5. **佐藤**でログイン → 田中の活動届 URL (`/reports/1`) を開く → 403 で見られない
6. **山本 (顧問)** で参加者名簿をダウンロードしようとする → 403

同じことを自動でチェックするテストがあります:

```bash
pytest -v
```

## フォルダ構成

```
activity-safety-app/
├── app/
│   ├── main.py            # 起動・ルーティング
│   ├── config.py          # 設定 (.env を読む)
│   ├── models.py          # DB テーブル定義 (活動届・団体台帳・名簿・通知・監査ログ)
│   ├── auth/
│   │   ├── base.py        # ユーザーと権限 (4章)
│   │   ├── dev.py         # 疑似ログイン (ローカル検証用)
│   │   └── entra.py       # Entra ID (未実装の枠。実装手順をコメントに記載)
│   ├── services/
│   │   ├── intake.py      # 受付後処理・判定ルール・結果通知 (8章)
│   │   ├── storage.py     # 添付の振分け (行程等 → 活動資料 / 名簿 → 限定保管先)
│   │   └── notify.py      # 通知 (今は DB 記録。SMTP や Graph に差し替え可)
│   ├── routers/           # 画面ごとの処理 (活動届・団体台帳・年度名簿・通知)
│   ├── templates/         # HTML
│   └── static/style.css
├── tests/test_acceptance.py  # 受入シナリオの自動テスト
├── seed.py                # サンプル団体の投入
├── requirements.txt
└── .env.example           # 設定例
```

## Entra ID 認証に切り替えるとき

`app/auth/entra.py` のコメントに手順を書いています。概要:

1. `pip install msal`
2. Entra ID にアプリ登録 (リダイレクト URI: `http://localhost:8000/auth/callback`)
3. `.env` に `AUTH_MODE=entra` とテナント ID / クライアント ID / シークレットを設定
4. `entra.py` の `/auth/login` と `/auth/callback` を実装し、取得したメール・氏名を `login_user()` に渡す
5. 役割 (学生/職員など) は Entra ID のグループかアプリロール、またはアプリ側の職員メール一覧で決める

画面や業務処理は `app/auth/base.py` の `User` しか見ていないので、他は変更不要です。

## 要件書との対応で意図的に簡略化した点

- **メール送信**はしていません (通知画面に記録)。本番では `services/notify.py` を差し替えます。
- **DB は SQLite** (ファイル 1 つ)。本番で複数人が同時に使うなら PostgreSQL 等に変えます (`DATABASE_URL` を変えるだけ)。
- 学生が「自分が提出した活動届」を見られるようにしています (要件書では将来検討の範囲ですが、検証しやすさのため)。他団体・他人の届は見えません。
- 添付ファイルの上限は 20MB です。
