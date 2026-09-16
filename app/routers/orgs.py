"""7.2 団体台帳の保守 (指定職員・システム保守担当)"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.base import User, current_user, forbidden
from ..database import get_db
from ..models import Organization

router = APIRouter(prefix="/orgs", tags=["orgs"])


def _tpl():
    from ..main import templates

    return templates


def _require(user: User) -> None:
    if not user.can_manage_orgs:
        raise forbidden("団体台帳の保守は指定職員・システム保守担当のみ行えます")


@router.get("")
def list_orgs(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require(user)
    orgs = list(db.scalars(select(Organization).order_by(Organization.is_active.desc(), Organization.name)))
    return _tpl().TemplateResponse(request, "orgs.html", {"user": user, "orgs": orgs})


@router.get("/new")
def new_org(request: Request, user: User = Depends(current_user)):
    _require(user)
    return _tpl().TemplateResponse(request, "org_form.html", {"user": user, "org": None, "error": ""})


@router.get("/{org_id}/edit")
def edit_org(org_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require(user)
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="団体が見つかりません")
    return _tpl().TemplateResponse(request, "org_form.html", {"user": user, "org": org, "error": ""})


@router.post("/save")
def save_org(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
             org_id: int | None = Form(None), name: str = Form(...), org_code: str = Form(...),
             rep_email: str = Form(""), vice_rep_email: str = Form(""), advisor_email: str = Form(""),
             is_active: str = Form("")):
    _require(user)
    org = db.get(Organization, org_id) if org_id else Organization()
    if org is None:
        raise HTTPException(status_code=404, detail="団体が見つかりません")
    dup = db.scalar(select(Organization).where(Organization.org_code == org_code.strip()))
    if dup is not None and dup.id != org.id:
        return _tpl().TemplateResponse(request, "org_form.html", {"user": user, "org": org, "error": "その団体IDは既に使われています"}, status_code=400)
    org.name = name.strip()
    org.org_code = org_code.strip()
    org.rep_email = rep_email.strip()
    org.vice_rep_email = vice_rep_email.strip()
    org.advisor_email = advisor_email.strip()
    org.is_active = is_active == "on"
    db.add(org)
    db.commit()
    return RedirectResponse("/orgs", status_code=303)
