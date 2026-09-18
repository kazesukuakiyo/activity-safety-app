"""Entra ID 認証をアプリ自身で行う場合の枠 (MSAL 方式)。**通常は使わない。**

Azure App Service に置くなら、Azure 側の「認証」機能を使う app/auth/easyauth.py の方が
シークレット管理もコードも不要で簡単。docs/DEPLOY_AZURE.md を参照。

Azure App Service 以外 (学内サーバーなど) で動かす必要が出たときだけ、ここを実装する:
  1. pip install msal
  2. Entra ID にアプリ登録し、リダイレクト URI に https://<ホスト>/auth/callback を登録
  3. 環境変数 ENTRA_TENANT_ID / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET を設定し AUTH_MODE=entra
  4. /auth/login  … msal.ConfidentialClientApplication.get_authorization_request_url() へリダイレクト
     /auth/callback … acquire_token_by_authorization_code() で ID トークンを取得し、
                       claims["preferred_username"] と claims["name"] から User を作って login_user()
     役割は easyauth.resolve_role() をそのまま使える
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(request: Request):
    raise HTTPException(status_code=501, detail="MSAL 方式の Entra ID 認証は未実装です。Azure では AUTH_MODE=easyauth を使ってください。")


@router.get("/callback")
def callback(request: Request):
    raise HTTPException(status_code=501, detail="MSAL 方式の Entra ID 認証は未実装です。")
