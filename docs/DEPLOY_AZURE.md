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

### 人と権限

| 必要なもの | 誰が用意するか | 備考 |
|---|---|---|
| 大学の Azure サブスクリプション | 情報システム部門 | 個人契約の Azure は使わない。教育機関向けの契約 (EES / Azure for Education) があれば割引が効くことが多い |
| リソース グループへの「共同作成者」権限 | 情報システム部門があなたに付与 | これがあれば App Service を自分で作れる |
| Entra ID の「アプリの登録」を作る権限 | 情報システム部門 | ログイン機能に必要。自分で作れない大学が多いので、依頼して作ってもらう (下記の依頼文) |
| GitHub の大学 Organization とリポジトリ | あなた + 情報システム部門 | 「デプロイ センター」で GitHub にログインする人が、そのリポジトリの管理者である必要がある |
| 職員のメールアドレス一覧 | 学生支援課 | 役割の割り当て (`STAFF_EMAILS` など) に使う |

情報システム部門への依頼文の例:

> 学生支援課の学外活動届システム (Web アプリ) を Azure App Service で運用したい。
> (1) サブスクリプション内にリソース グループ `rg-activity-safety` を作り、私に共同作成者権限を付与してほしい。
> (2) App Service の認証機能で Entra ID ログインを使うため、アプリの登録を 1 つ作ってほしい。
>     名前: activity-safety-app、アカウントの種類: この組織のみ、
>     リダイレクト URI: `https://<アプリ名>.azurewebsites.net/.auth/login/aad/callback`
> (3) 将来メール通知を送るため、Microsoft Graph の Mail.Send 権限の付与を相談したい (今は不要)。

### Azure に作るもの

| 段階 | リソース | 用途 |
|---|---|---|
| 最初 | **App Service プラン + Web アプリ** (Linux, Python 3.12) | アプリ本体。DB (SQLite) と添付もこの中の `/home/data` に置く |
| 最初 | **Entra ID アプリの登録** | ログイン。App Service の「認証」から自動作成、または上記の依頼で作成 |
| 最初 | **GitHub との接続** (デプロイ センター) | push で自動配備 |
| 任意 | **Application Insights** | 稼働監視・エラー通知 |
| 任意 | **予算アラート** (コスト管理) | 月額が想定を超えたらメール |
| 後で | **Azure Database for PostgreSQL** (Flexible Server) | 同時利用が増えたとき |
| 後で | **ストレージ アカウント (Blob)** | 添付ファイルを App Service の外に出すとき |
| 後で | **カスタム ドメイン + 証明書** | `katsudo.univ.ac.jp` のような URL にするとき。証明書は App Service の無料のもので可 |

### 費用の目安

概算です (2026 年時点の一般的な価格帯、Japan East、税別)。**必ず Azure の料金計算ツールで「Japan East・JPY」を選んで確認してください。** 大学の教育機関契約があれば下がります。

| 構成 | 内訳 | 月額の目安 |
|---|---|---|
| **試験運用** (数団体で試す) | App Service Basic B1 (1 コア / 1.75 GB) | 約 2,000〜2,500 円 |
| **本番・小規模** (全団体、同時利用は少ない) | App Service Basic B2 または Standard S1 | 約 4,000〜10,000 円 |
| **本番・標準** (安定運用) | App Service Premium P0v3 + PostgreSQL Flexible Server B1ms (32GB) | 約 12,000〜16,000 円 |
| 追加 | Application Insights (少量なら無料枠内)、Blob Storage (数 GB で数十円)、通信量 (無視できる程度) | 0〜数百円 |

無料で済むもの: Entra ID のログイン機能 (App Service の認証は追加料金なし)、GitHub Actions (非公開リポジトリでも月 2,000 分まで無料)、App Service の無料 SSL 証明書。

年額にすると、試験運用で約 3 万円、本番の標準構成で約 15〜20 万円が目安です。サーバーの保守 (OS 更新など) は Azure 側が行うので、人件費以外の維持費はこれだけです。

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
