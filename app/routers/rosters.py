"""3.2 年度部員名簿。団体 × 年度ごとに「学籍番号・氏名・所属・学年」の表として保持する。

提出方法:
  - 大学指定の Excel テンプレートをダウンロード → 記入 → アップロード → プレビュー確認 → 保存
  - (補助) Excel からコピーして貼り付け
権限:
  - 学生: 自分が代表者・副代表者の団体だけ登録・閲覧できる (他団体は 403)
  - 指定職員: 受領済みの名簿を任意の団体に取り込める。全団体を閲覧できる
  - 管理職: 全団体を閲覧のみ
  - 顧問・システム保守担当: 閲覧不可
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.base import User, current_user, forbidden
from ..database import get_db
from ..models import Member, Organization
from ..services.roster import RosterError, build_template_xlsx, parse_roster_file, parse_roster_text, rows_to_text, to_csv

router = APIRouter(prefix="/rosters", tags=["rosters"])

MAX_FILE_BYTES = 5 * 1024 * 1024


def _tpl():
    from ..main import templates

    return templates


def _fiscal_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def _my_orgs(db: Session, user: User) -> list[Organization]:
    orgs = db.scalars(select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.name)).all()
    return [o for o in orgs if o.is_representative(user.email)]


def can_write(user: User, org: Organization) -> bool:
    return user.can_edit_reports or (user.can_submit and org.is_representative(user.email))


def can_read(user: User, org: Organization) -> bool:
    return user.can_view_rosters or (user.can_submit and org.is_representative(user.email))


def _org_for(db: Session, user: User, org_id: int, *, write: bool) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="団体が見つかりません")
    if write and not can_write(user, org):
        raise forbidden("この団体の名簿を登録できるのは、その団体の代表者・副代表者と指定職員だけです")
    if not write and not can_read(user, org):
        raise forbidden("この団体の名簿を閲覧する権限がありません")
    return org


def _members(db: Session, org: Organization, fy: int) -> list[Member]:
    return db.scalars(select(Member).where(Member.organization_id == org.id, Member.fiscal_year == fy).order_by(Member.student_no)).all()


def _render(request: Request, user: User, org: Organization, members: list[Member], fy: int, *,
            error: str = "", preview=None, preview_text: str = "", preview_source: str = "", status_code: int = 200):
    return _tpl().TemplateResponse(request, "roster_org.html", {
        "user": user, "org": org, "members": members, "fiscal_year": fy, "can_edit": can_write(user, org),
        "error": error, "preview": preview, "preview_text": preview_text, "preview_source": preview_source,
    }, status_code=status_code)


@router.get("/template.xlsx")
def template_xlsx(user: User = Depends(current_user), db: Session = Depends(get_db), org_id: int | None = None, fiscal_year: int | None = None):
    """大学指定の名簿テンプレート"""
    org_name = ""
    if org_id:
        org = db.get(Organization, org_id)
        org_name = org.name if org else ""
    data = build_template_xlsx(org_name, fiscal_year or _fiscal_year())
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="roster_template.xlsx"'})


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
def org_roster(org_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), fiscal_year: int | None = None):
    fy = fiscal_year or _fiscal_year()
    org = _org_for(db, user, org_id, write=False)
    return _render(request, user, org, _members(db, org, fy), fy)


@router.post("/{org_id}/upload")
async def upload(org_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
                 fiscal_year: int = Form(...), file: UploadFile | None = None):
    """ファイルを解析してプレビューを表示する (まだ保存しない)。"""
    org = _org_for(db, user, org_id, write=True)
    members = _members(db, org, fiscal_year)
    data = await file.read() if file and file.filename else b""
    if not data:
        return _render(request, user, org, members, fiscal_year, error="ファイルを選んでください", status_code=400)
    if len(data) > MAX_FILE_BYTES:
        return _render(request, user, org, members, fiscal_year, error="ファイルが大きすぎます (5MB まで)", status_code=400)
    try:
        rows = parse_roster_file(file.filename, data)
    except RosterError as e:
        return _render(request, user, org, members, fiscal_year, error=str(e), status_code=400)
    if not rows:
        return _render(request, user, org, members, fiscal_year, error="名簿の行が見つかりませんでした。テンプレートの「部員名簿」シートに記入してください", status_code=400)
    return _render(request, user, org, members, fiscal_year, preview=rows, preview_text=rows_to_text(rows), preview_source=file.filename)


@router.post("/{org_id}")
def save_roster(org_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
                fiscal_year: int = Form(...), roster_text: str = Form("")):
    """プレビュー確認後 (または貼り付け) の保存。その年度の名簿を丸ごと置き換える。"""
    org = _org_for(db, user, org_id, write=True)
    try:
        rows = parse_roster_text(roster_text)
    except RosterError as e:
        return _render(request, user, org, _members(db, org, fiscal_year), fiscal_year, error=str(e), status_code=400)
    for m in _members(db, org, fiscal_year):
        db.delete(m)
    db.flush()
    for r in rows:
        db.add(Member(organization_id=org.id, fiscal_year=fiscal_year, student_no=r.student_no, name=r.name,
                      department=r.department, grade=r.grade, registered_by=user.email))
    db.commit()
    return RedirectResponse(f"/rosters/{org.id}?fiscal_year={fiscal_year}&saved=1", status_code=303)


@router.get("/{org_id}/members.json")
def members_json(org_id: int, user: User = Depends(current_user), db: Session = Depends(get_db), fiscal_year: int | None = None):
    """活動届フォームで「年度部員名簿から選ぶ」ために使う。代表者・副代表者の団体だけ返す。"""
    fy = fiscal_year or _fiscal_year()
    org = db.get(Organization, org_id)
    if org is None or not (user.can_submit and org.is_representative(user.email)):
        return JSONResponse({"members": [], "allowed": False})
    members = _members(db, org, fy)
    return JSONResponse({"allowed": True, "fiscal_year": fy,
                         "members": [{"id": m.id, "student_no": m.student_no, "name": m.name, "department": m.department, "grade": m.grade} for m in members]})


@router.get("/{org_id}/members.csv")
def members_csv(org_id: int, user: User = Depends(current_user), db: Session = Depends(get_db), fiscal_year: int | None = None):
    fy = fiscal_year or _fiscal_year()
    org = _org_for(db, user, org_id, write=False)
    return Response(to_csv(_members(db, org, fy)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{org.org_code}_{fy}_members.csv"'})
