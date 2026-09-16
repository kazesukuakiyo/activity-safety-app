"""3.2 年度部員名簿。団体 × 年度ごとに「学籍番号・氏名・所属・学年」の表として保持する。

- 学生 (その団体の代表者・副代表者) が登録・更新できる
- 指定職員・管理職は全団体分を閲覧できる
- 顧問・システム保守担当は閲覧できない
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.base import User, current_user, forbidden
from ..database import get_db
from ..models import Member, Organization
from ..services.roster import RosterError, parse_roster_text, rows_to_text, to_csv

router = APIRouter(prefix="/rosters", tags=["rosters"])


def _tpl():
    from ..main import templates

    return templates


def _fiscal_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def _my_orgs(db: Session, user: User) -> list[Organization]:
    orgs = db.scalars(select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.name)).all()
    return [o for o in orgs if o.is_representative(user.email)]


def _org_for(db: Session, user: User, org_id: int, *, write: bool) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="団体が見つかりません")
    if write:
        if not (user.can_submit and org.is_representative(user.email)):
            raise forbidden("年度部員名簿を登録できるのは、その団体の代表者・副代表者だけです")
    elif not (user.can_view_rosters or (user.can_submit and org.is_representative(user.email))):
        raise forbidden("この団体の名簿を閲覧する権限がありません")
    return org


@router.get("")
def index(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), fiscal_year: int | None = None):
    fy = fiscal_year or _fiscal_year()
    if user.can_view_rosters:
        orgs = db.scalars(select(Organization).order_by(Organization.is_active.desc(), Organization.name)).all()
    elif user.can_submit:
        orgs = _my_orgs(db, user)
    else:
        raise forbidden("名簿保管先を閲覧する権限がありません")
    counts = dict(db.execute(select(Member.organization_id, func.count()).where(Member.fiscal_year == fy).group_by(Member.organization_id)).all())
    return _tpl().TemplateResponse(request, "rosters.html", {"user": user, "orgs": orgs, "counts": counts, "fiscal_year": fy})


@router.get("/{org_id}")
def org_roster(org_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
               fiscal_year: int | None = None, error: str = ""):
    fy = fiscal_year or _fiscal_year()
    org = _org_for(db, user, org_id, write=False)
    members = db.scalars(select(Member).where(Member.organization_id == org.id, Member.fiscal_year == fy).order_by(Member.student_no)).all()
    can_edit = user.can_submit and org.is_representative(user.email)
    return _tpl().TemplateResponse(request, "roster_org.html", {
        "user": user, "org": org, "members": members, "fiscal_year": fy, "can_edit": can_edit,
        "roster_text": rows_to_text(members), "error": error,
    })


@router.post("/{org_id}")
def save_roster(org_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
                fiscal_year: int = Form(...), roster_text: str = Form("")):
    """貼り付けた内容で、その年度の名簿を丸ごと置き換える (加入・退部の更新もこれで行う)。"""
    org = _org_for(db, user, org_id, write=True)
    try:
        rows = parse_roster_text(roster_text)
    except RosterError as e:
        members = db.scalars(select(Member).where(Member.organization_id == org.id, Member.fiscal_year == fiscal_year)).all()
        return _tpl().TemplateResponse(request, "roster_org.html", {
            "user": user, "org": org, "members": members, "fiscal_year": fiscal_year, "can_edit": True,
            "roster_text": roster_text, "error": str(e),
        }, status_code=400)
    for m in db.scalars(select(Member).where(Member.organization_id == org.id, Member.fiscal_year == fiscal_year)):
        db.delete(m)
    db.flush()
    for r in rows:
        db.add(Member(organization_id=org.id, fiscal_year=fiscal_year, student_no=r.student_no, name=r.name,
                      department=r.department, grade=r.grade, registered_by=user.email))
    db.commit()
    return RedirectResponse(f"/rosters/{org.id}?fiscal_year={fiscal_year}", status_code=303)


@router.get("/{org_id}/members.json")
def members_json(org_id: int, user: User = Depends(current_user), db: Session = Depends(get_db), fiscal_year: int | None = None):
    """活動届フォームで「部員一覧から選ぶ」ために使う。代表者・副代表者の団体だけ返す。"""
    fy = fiscal_year or _fiscal_year()
    org = db.get(Organization, org_id)
    if org is None or not (user.can_submit and org.is_representative(user.email)):
        return JSONResponse({"members": [], "allowed": False})
    members = db.scalars(select(Member).where(Member.organization_id == org.id, Member.fiscal_year == fy).order_by(Member.student_no)).all()
    return JSONResponse({"allowed": True, "fiscal_year": fy,
                         "members": [{"id": m.id, "student_no": m.student_no, "name": m.name, "department": m.department, "grade": m.grade} for m in members]})


@router.get("/{org_id}/members.csv")
def members_csv(org_id: int, user: User = Depends(current_user), db: Session = Depends(get_db), fiscal_year: int | None = None):
    fy = fiscal_year or _fiscal_year()
    org = _org_for(db, user, org_id, write=False)
    members = db.scalars(select(Member).where(Member.organization_id == org.id, Member.fiscal_year == fy).order_by(Member.student_no)).all()
    return Response(to_csv(members), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{org.org_code}_{fy}_members.csv"'})
