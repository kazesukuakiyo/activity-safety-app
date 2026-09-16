"""Entra ID (旧 Azure AD) 認証。**未実装の枠** です。

後で実装するときの流れ (Authorization Code Flow):
  1. pip install msal
  2. Entra ID にアプリ登録し、リダイレクト URI に http://localhost:8000/auth/callback を登録
  3. .env に ENTRA_TENANT_ID / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET を設定し AUTH_MODE=entra
  4. /auth/login  … msal.ConfidentialClientApplication.get_authorization_request_url() へリダイレクト
     /auth/callback … acquire_token_by_authorization_code() で ID トークンを取得し、
                       claims["preferred_username"] (メール) と claims["name"] を User に詰めて login_user()
  5. 役割 (Role) の決め方は運用次第:
       - Entra ID のアプリロール / グループ (claims["roles"] や "groups") で判定する
       - または本アプリ側に「職員メール一覧」テーブルを持ち、メールで判定する (既定は学生)

画面や業務ロジックは app/auth/base.py の User だけを見ているので、ここを実装すれば他は変更不要。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(request: Request):
    raise HTTPException(status_code=501, detail="Entra ID 認証は未実装です。AUTH_MODE=dev でローカル検証してください。")


@router.get("/callback")
def callback(request: Request):
    raise HTTPException(status_code=501, detail="Entra ID 認証は未実装です。")
