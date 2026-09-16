"""3.2 年度部員名簿。活動届とは別フォームで年1回提出し、限定保管先に置く。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.base import User, current_user, forbidden
from ..database import get_db
from ..models import AnnualRoster, Organization
from ..services import storage

router = APIRouter(prefix="/rosters", tags=["rosters"])


def _tpl():
    from ..main import templates

    return templates


def _fiscal_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


@router.get("")
def list_rosters(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.can_view_rosters:
        rosters = list(db.scalars(select(AnnualRoster).order_by(AnnualRoster.fiscal_year.desc(), AnnualRoster.id.desc())))
    elif user.can_submit:
        rosters = list(db.scalars(select(AnnualRoster).where(AnnualRoster.submitted_by_email == user.email).order_by(AnnualRoster.id.desc())))
    else:
        raise forbidden("名簿保管先を閲覧する権限がありません")
    orgs = list(db.scalars(select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.name)))
    return _tpl().TemplateResponse(request, "rosters.html", {"user": user, "rosters": rosters, "orgs": orgs, "fiscal_year": _fiscal_year(), "error": ""})


@router.post("/new")
async def submit_roster(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
                        organization_id: int = Form(...), fiscal_year: int = Form(...), note: str = Form(""),
                        file: UploadFile = None):
    if not user.can_submit:
        raise forbidden("年度部員名簿の提出は学生・団体代表者のみ行えます")
    org = db.get(Organization, organization_id)
    if org is None or not org.is_active:
        raise HTTPException(status_code=400, detail="団体を選択してください")
    data = await file.read() if file and file.filename else b""
    if not data:
        raise HTTPException(status_code=400, detail="名簿ファイルを添付してください")
    rel, _ = storage.save_roster_file(org.org_code, fiscal_year, file.filename, data)
    db.add(AnnualRoster(organization_id=org.id, fiscal_year=fiscal_year, original_name=file.filename,
                        stored_path=rel, submitted_by_email=user.email, note=note.strip()))
    db.commit()
    return RedirectResponse("/rosters", status_code=303)


@router.get("/{roster_id}/download")
def download(roster_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.can_view_rosters:
        raise forbidden("年度部員名簿は指定職員・管理職のみ閲覧できます")
    roster = db.get(AnnualRoster, roster_id)
    if roster is None:
        raise HTTPException(status_code=404, detail="名簿が見つかりません")
    return FileResponse(storage.resolve(roster.stored_path), filename=roster.original_name)
