# Azure に載せる手順 (はじめての人向け)

このアプリを大学の Microsoft 環境 (Azure) で動かし、Entra ID (大学アカウント) でログインできるようにする手順です。
**コードは書きません。Azure の画面でボタンを押していくだけです。** 所要時間は、慣れていなければ 1〜2 時間です。

## 全体像

```
学生・職員のブラウザ
      │  https://xxxx.azurewebsites.net
      ▼
Azure App Service ─── 「認証」機能が Entra ID ログインを肩代わり
      │  (ログイン済みの人だけがアプリに届く)
      ▼
このアプリ (GitHub から自動で配備される)
      │
      ├── DB      … 最初は App Service 内の SQLite。人数が増えたら PostgreSQL
      └── 添付    … App Service 内の /home/data (再起動しても消えない)
```

## 事前に必要なもの

| もの | 確認方法 |
|---|---|
| 大学の Azure サブスクリプション | 情報システム部門に「Azure のサブスクリプションで App Service を 1 つ作りたい」と相談する。個人契約の Azure は使わない |
| Azure ポータルにログインできる大学アカウント | https://portal.azure.com を開いてログインできるか |
| GitHub のリポジトリ | 大学名義に移した後のもの (個人アカウントのままなら先に移管) |

費用の目安 (2026 年時点、東日本リージョン):

| 用途 | プラン | 月額 |
|---|---|---|
| 試験運用 | App Service **B1** | 約 2,000 円 |
| 本番 (数百団体) | App Service **P0v3** + PostgreSQL Flexible Server B1ms | 約 10,000 円 |

無料プラン (F1) は「認証」機能とカスタム起動コマンドが制限されるので使いません。

---

## ステップ 1: Web アプリを作る (10 分)

1. https://portal.azure.com を開く
2. 上の検索窓に **App Service** と入れて開く → **「+ 作成」→「Web アプリ」**
3. 次のように入力する

| 項目 | 入れる値 |
|---|---|
| サブスクリプション | 大学のもの |
| リソース グループ | 「新規作成」→ `rg-activity-safety` |
| 名前 | `activity-safety-<大学の略称>` (これが URL になる。世界で一意) |
| 公開 | **コード** |
| ランタイム スタック | **Python 3.12** |
| オペレーティング システム | **Linux** |
| リージョン | **Japan East** |
| 価格プラン | **Basic B1** (試験運用) |

4. **「確認および作成」→「作成」**。1〜2 分待つ
5. できたら **「リソースに移動」**

## ステップ 2: GitHub とつなぐ (10 分)

push すると自動で配備される仕組みを作ります。

1. 左メニュー **「デプロイ センター」**
2. ソース: **GitHub** → 「承認」で GitHub にログイン
3. 組織 / リポジトリ / ブランチ (`main`) を選ぶ
4. 認証の種類は **「ユーザー割り当て ID」**(既定) のまま
5. **「保存」**

これで GitHub に `.github/workflows/main_activity-safety-xxx.yml` というファイルが自動で追加され、最初の配備が始まります。
GitHub の **Actions** タブで進み具合が見えます (5 分ほど)。

> この自動追加されたファイルは消さないでください。今後 `main` に push するたびに Azure が更新されます。

## ステップ 3: 起動コマンドと設定を入れる (10 分)

1. 左メニュー **「設定」→「環境変数」** → **「アプリ設定」** タブで **「+ 追加」** を繰り返す

| 名前 | 値 | 意味 |
|---|---|---|
| `AUTH_MODE` | `easyauth` | Azure の認証機能を使う |
| `APP_SECRET_KEY` | 長いランダム文字列 (下のコマンドで作る) | Cookie の署名用 |
| `DATA_DIR` | `/home/data` | DB と添付の保存先 (再起動で消えない場所) |
| `DATABASE_URL` | `sqlite:////home/data/app.db` | 最初は SQLite。スラッシュは 4 つ |
| `RUN_MIGRATIONS_ON_STARTUP` | `0` | 起動コマンド側で DB 更新するため |
| `STAFF_NOTIFY_EMAIL` | 学生支援課の代表メール | 職員向け通知の宛先 |
| `STAFF_EMAILS` | `taro@univ.ac.jp,hanako@univ.ac.jp` | 指定職員のメール (カンマ区切り) |
| `MANAGER_EMAILS` | `kacho@univ.ac.jp` | 管理職 (閲覧のみ) |
| `SYSADMIN_EMAILS` | `you@univ.ac.jp` | システム保守 |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` | 配備時にライブラリを入れる |
| `WEBSITE_HTTPLOGGING_RETENTION_DAYS` | `7` | ログ保持 |

`APP_SECRET_KEY` はターミナルで次を実行して出た文字列を使います:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

顧問は設定不要です (団体台帳の顧問メールで自動判定)。上のどれにも無い大学アカウントは学生として扱われます。

2. **「適用」** を押す
3. 左メニュー **「設定」→「構成」** → **「全般設定」** タブ → **スタートアップ コマンド** に次を入れて **「保存」**

```
bash startup.sh
```

4. 同じ画面の **「ヘルス チェック」** を「有効」にし、パスに `/healthz` を入れて保存 (任意)

## ステップ 4: Entra ID ログインを付ける (10 分)

1. 左メニュー **「設定」→「認証」** → **「ID プロバイダーを追加」**
2. ID プロバイダー: **Microsoft**
3. 次のように選ぶ

| 項目 | 値 |
|---|---|
| テナントの種類 | **従業員** |
| アプリの登録 | **新しいアプリの登録を作成する** |
| 名前 | `activity-safety-app` |
| サポートされているアカウントの種類 | **現在のテナントのみ** (= 大学アカウントだけ) |
| 認証されていない要求 | **HTTP 302 リダイレクト (Web サイトに推奨)** |
| トークン ストア | オン |

4. **「追加」**

これだけで、URL を開いた人は大学のログイン画面に飛ばされ、ログイン後にアプリが開きます。
アプリは Azure が付ける「ログインした人のメールアドレス」を読んで役割を決めます。

> アプリの登録を「新しく作成」できない場合 (大学が制限している) は、情報システム部門に
> 「App Service の認証用に Entra ID アプリ登録を 1 つ作ってほしい。リダイレクト URI は
> `https://<アプリ名>.azurewebsites.net/.auth/login/aad/callback`」と依頼し、
> 「既存のアプリの登録を選択する」で選びます。

## ステップ 5: 動作確認 (10 分)

1. **「概要」** の **既定のドメイン** (`https://activity-safety-xxx.azurewebsites.net`) を開く
2. 大学アカウントでログインする
3. 自分のメールを `STAFF_EMAILS` に入れていれば、ダッシュボードが開く
4. 左メニュー **「監視」→「ログ ストリーム」** でエラーが出ていないか見る

**団体台帳を登録する**: 職員でログイン → 「団体台帳」→ 団体を追加 (Excel から一括で入れたい場合は別途相談)。
学生 (代表者) が自分のメールで入ると、その団体だけが選べるようになります。

## うまくいかないとき

| 症状 | 見るところ |
|---|---|
| 「Application Error」と出る | 「ログ ストリーム」。多いのは環境変数の入れ忘れ、起動コマンドの未設定 |
| ログインループする | 「認証」の「認証されていない要求」が 302 になっているか |
| 全員が学生扱いになる | `STAFF_EMAILS` のメールが、ログイン画面に出るアドレスと同じか (大文字小文字は無視される) |
| 配備が失敗する | GitHub の Actions タブの赤い実行を開く。`requirements.txt` のライブラリが入らないときはランタイムを Python 3.12 にする |
| 添付が消えた | `DATA_DIR` が `/home/data` になっているか (`/home` 以外は再起動で消える) |

## 本番に向けた次の一手

1. **PostgreSQL に切り替える** (同時利用が増えたら)
   Azure Database for PostgreSQL Flexible Server (Burstable B1ms) を作り、
   `DATABASE_URL` を `postgresql+psycopg://ユーザー:パスワード@ホスト:5432/DB名?sslmode=require` に変えて再起動するだけ。
   `startup.sh` がテーブルを自動で作ります。
2. **メール通知**: Microsoft Graph (大学の Exchange) で送る。`app/services/notify.py` の 1 関数を差し替え。
3. **添付を Blob Storage へ**: 複数インスタンスにするとき。`app/services/storage.py` を差し替え。
4. **バックアップ**: App Service の「バックアップ」を有効化 (SQLite のうちはこれで足りる)。
5. **カスタム ドメイン**: `katsudo.univ.ac.jp` のような URL にしたければ「カスタム ドメイン」から。
