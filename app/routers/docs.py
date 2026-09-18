"""設計書・要件定義書・手順書をアプリ内で閲覧する (職員・管理職・保守担当)。

docs/ 配下の Markdown をそのまま表示するので、文書とコードを同じリポジトリで版管理できる。
"""

from __future__ import annotations

from pathlib import Path

import markdown
from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.base import User, current_user, forbidden
from ..config import BASE_DIR

router = APIRouter(prefix="/docs", tags=["docs"])

# 表示名, ファイル, 説明 (この一覧に無いファイルは表示しない)
DOCUMENTS: dict[str, tuple[str, Path, str]] = {
    "design": ("設計書", BASE_DIR / "docs" / "DESIGN.md", "画面・業務ルール・データ・権限・要件との対応表"),
    "requirements": ("要件定義書 v3.0", BASE_DIR / "docs" / "REQUIREMENTS.md", "元となった要件定義書 (Word 版を変換)"),
    "readme": ("使い方", BASE_DIR / "README.md", "起動方法・検証用ユーザー・動作確認の流れ"),
    "deploy": ("Azure 配備手順", BASE_DIR / "docs" / "DEPLOY_AZURE.md", "大学の Microsoft 環境に載せる手順"),
    "development": ("開発者向けメモ", BASE_DIR / "docs" / "DEVELOPMENT.md", "コードの直し方・DB 変更の手順"),
}


def _require(user: User) -> None:
    if not user.can_view_all_reports:
        raise forbidden("設計書・手順書は職員・管理職・システム保守担当のみ閲覧できます")


@router.get("")
def index(request: Request, user: User = Depends(current_user)):
    _require(user)
    from ..main import templates

    return templates.TemplateResponse(request, "docs.html", {"user": user, "documents": DOCUMENTS, "current": None, "body": ""})


@router.get("/{name}")
def show(name: str, request: Request, user: User = Depends(current_user)):
    _require(user)
    from ..main import templates

    if name not in DOCUMENTS:
        raise HTTPException(status_code=404, detail="文書が見つかりません")
    title, path, _ = DOCUMENTS[name]
    if not path.exists():
        raise HTTPException(status_code=404, detail="文書ファイルがありません")
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists"], extension_configs={"toc": {"toc_depth": "2-3"}}, output_format="html5"
    )
    body = md.convert(path.read_text(encoding="utf-8"))
    return templates.TemplateResponse(
        request, "docs.html", {"user": user, "documents": DOCUMENTS, "current": name, "title": title, "body": body, "toc": md.toc}
    )
