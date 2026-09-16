"""活動届: 学生の提出フォーム / 職員の一覧・詳細・状況更新"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.base import Role, User, current_user, forbidden
from ..database import get_db
from ..models import ActivityReport, Attachment, AttachmentKind, Organization, ReportStatus
from ..services import intake, storage

router = APIRouter(prefix="/reports", tags=["reports"])

MAX_FILE_BYTES = 20 * 1024 * 1024


def _tpl():
    from ..main import templates

    return templates


def _parse_dt(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label}の形式が正しくありません")


def _active_orgs(db: Session) -> list[Organization]:
    return list(db.scalars(select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.name)))


def _can_view(user: User, report: ActivityReport) -> bool:
    if user.can_view_all_reports:
        return True
    if user.role == Role.ADVISOR:
        return report.organization.advisor_email.lower() == user.email.lower()
    return report.applicant_email.lower() == user.email.lower()


# ------------------------------------------------------------ 学生: 提出フォーム
@router.get("/new")
def new_form(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.can_submit:
        raise forbidden("活動届の提出は学生・団体代表者のみ行えます")
    return _tpl().TemplateResponse(request, "report_form.html", {"user": user, "orgs": _active_orgs(db), "errors": [], "form": {}})


@router.post("/new")
async def submit(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    organization_id: int = Form(...),
    content: str = Form(...),
    start_at: str = Form(...),
    end_at: str = Form(...),
    location: str = Form(...),
    participants_count: int = Form(...),
    leader_name: str = Form(...),
    leader_phone: str = Form(...),
    leader_email: str = Form(...),
    requires_precheck: str = Form(...),
    itinerary_summary: str = Form(""),
    declared_docs: list[str] = Form([]),
    notes_to_university: str = Form(""),
    itinerary_files: list[UploadFile] = [],
    roster_files: list[UploadFile] = [],
    other_files: list[UploadFile] = [],
):
    if not user.can_submit:
        raise forbidden("活動届の提出は学生・団体代表者のみ行えます")

    org = db.get(Organization, organization_id)
    errors: list[str] = []
    if org is None or not org.is_active:
        errors.append("団体を選択してください")
    start = _parse_dt(start_at, "開始日時")
    end = _parse_dt(end_at, "終了日時")
    if end < start:
        errors.append("終了日時は開始日時より後にしてください")
    if participants_count < 1:
        errors.append("参加予定人数は1以上にしてください")
    if errors:
        form = dict(await request.form())
        return _tpl().TemplateResponse(request, "report_form.html", {"user": user, "orgs": _active_orgs(db), "errors": errors, "form": form}, status_code=400)

    report = ActivityReport(
        organization_id=org.id,
        content=content.strip(),
        start_at=start,
        end_at=end,
        location=location.strip(),
        participants_count=participants_count,
        leader_name=leader_name.strip(),
        leader_phone=leader_phone.strip(),
        leader_email=leader_email.strip(),
        requires_precheck=(requires_precheck == "yes"),
        itinerary_summary=itinerary_summary.strip(),
        declared_itinerary=("itinerary" in declared_docs),
        declared_roster=("roster" in declared_docs),
        notes_to_university=notes_to_university.strip(),
        applicant_name=user.name,
        applicant_email=user.email,
        source="WebForm",
    )
    db.add(report)
    db.flush()  # id を確定させる (申請番号に使う)
    report.application_no = f"ACT-{report.id:06d}"

    # 添付振分け: 種別ごとに保管先を変える
    for kind, files in ((AttachmentKind.ITINERARY, itinerary_files), (AttachmentKind.ROSTER, roster_files), (AttachmentKind.OTHER, other_files)):
        for f in files:
            if not f.filename:
                continue
            data = await f.read()
            if not data:
                continue
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(status_code=400, detail=f"{f.filename} が大きすぎます (20MB まで)")
            rel, _ = storage.save_attachment(kind, report.application_no, f.filename, data)
            report.attachments.append(Attachment(kind=kind, original_name=f.filename, stored_path=rel,
                                                 is_restricted=storage.is_restricted(kind), size_bytes=len(data)))

    intake.process_new_report(db, report)
    db.commit()
    return RedirectResponse(f"/reports/{report.id}/done", status_code=303)


@router.get("/{report_id}/done")
def done(report_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    report = db.get(ActivityReport, report_id)
    if report is None or not _can_view(user, report):
        raise forbidden("この活動届を閲覧する権限がありません")
    return _tpl().TemplateResponse(request, "report_done.html", {"user": user, "report": report})


# ------------------------------------------------------------ 一覧 (職員は全件、学生は自分の分のみ)
@router.get("")
def list_reports(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
                 status: str = "", q: str = ""):
    stmt = select(ActivityReport).order_by(ActivityReport.id.desc())
    if user.can_view_all_reports:
        pass
    elif user.role == Role.ADVISOR:
        stmt = stmt.join(Organization).where(Organization.advisor_email == user.email)
    else:
        stmt = stmt.where(ActivityReport.applicant_email == user.email)
    if status:
        try:
            stmt = stmt.where(ActivityReport.status == ReportStatus(status))
        except ValueError:
            pass
    if q:
        like = f"%{q}%"
        stmt = stmt.where(ActivityReport.content.like(like) | ActivityReport.application_no.like(like) | ActivityReport.location.like(like))
    reports = list(db.scalars(stmt))
    return _tpl().TemplateResponse(request, "report_list.html", {"user": user, "reports": reports, "statuses": list(ReportStatus), "status": status, "q": q})


@router.get("/{report_id}")
def detail(report_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    report = db.get(ActivityReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="活動届が見つかりません")
    if not _can_view(user, report):
        raise forbidden("この活動届を閲覧する権限がありません")
    return _tpl().TemplateResponse(request, "report_detail.html", {"user": user, "report": report, "statuses": list(ReportStatus), "AttachmentKind": AttachmentKind})


@router.post("/{report_id}/status")
def update_status(report_id: int, user: User = Depends(current_user), db: Session = Depends(get_db),
                  status: str = Form(...), remarks: str = Form("")):
    if not user.can_edit_reports:
        raise forbidden("状況の更新は指定職員のみ行えます")
    report = db.get(ActivityReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="活動届が見つかりません")
    try:
        new_status = ReportStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail="状況の値が不正です")
    intake.update_status(db, report, user, new_status, remarks.strip())
    db.commit()
    return RedirectResponse(f"/reports/{report.id}", status_code=303)


@router.get("/{report_id}/attachments/{attachment_id}")
def download(report_id: int, attachment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    att = db.get(Attachment, attachment_id)
    if att is None or att.report_id != report_id:
        raise HTTPException(status_code=404, detail="添付が見つかりません")
    report = att.report
    if att.is_restricted:
        # 参加者名簿: 名簿閲覧権限 (職員・管理職) が必要。提出者本人も不可 (限定保管先)。
        if not user.can_view_rosters:
            raise forbidden("参加者名簿は指定職員・管理職のみ閲覧できます")
    elif not _can_view(user, report):
        raise forbidden("この添付を閲覧する権限がありません")
    return FileResponse(storage.resolve(att.stored_path), filename=att.original_name)
