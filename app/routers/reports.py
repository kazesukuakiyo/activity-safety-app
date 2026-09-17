"""活動届: 学生の提出・再提出フォーム / 職員の一覧・詳細・状況更新"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from ..auth.base import Role, User, current_user, forbidden
from ..database import get_db
from ..models import ActivityReport, Attachment, AttachmentKind, AuditLog, Member, Organization, Participant, ReportStatus
from ..services import intake, storage
from ..services.roster import RosterError, RosterRow, merge, parse_roster_text, rows_from_fields, to_csv

router = APIRouter(prefix="/reports", tags=["reports"])

MAX_FILE_BYTES = 20 * 1024 * 1024


def _tpl():
    from ..main import templates

    return templates


def _parse_dt(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label}の形式が正しくありません") from None


def _active_orgs(db: Session) -> list[Organization]:
    return list(db.scalars(select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.name)))


def _fiscal_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def _can_view(user: User, report: ActivityReport) -> bool:
    if user.can_view_all_reports:
        return True
    if user.role == Role.ADVISOR:
        return report.organization.advisor_email.lower() == user.email.lower()
    return report.applicant_email.lower() == user.email.lower()


def _can_view_participants(user: User, report: ActivityReport) -> bool:
    """参加者名簿は指定職員・管理職と、入力した提出者本人だけ。顧問・保守担当は不可。"""
    return user.can_view_rosters or report.applicant_email.lower() == user.email.lower()


def _is_owner(user: User, report: ActivityReport) -> bool:
    return user.can_submit and report.applicant_email.lower() == user.email.lower()


def _member_orgs_for(user: User, orgs: list[Organization]) -> list[int]:
    """部員一覧から参加者を選べる団体 = 自分が代表者・副代表者の団体"""
    return [o.id for o in orgs if o.is_representative(user.email)]


def _render_form(
    request: Request,
    user: User,
    db: Session,
    *,
    report: ActivityReport | None,
    errors: list[str],
    form: dict,
    status_code: int = 200,
):
    orgs = _active_orgs(db)
    my_org_ids = _member_orgs_for(user, orgs)
    my_orgs = [o for o in orgs if o.id in my_org_ids]
    selected = str(form.get("organization_id") or "")
    # 自分の団体が無い、または選択済みの団体が自分の団体でない (再提出など) ときは最初から全団体を出す
    show_all = not my_orgs or (selected != "" and selected not in {str(i) for i in my_org_ids})
    if not selected and len(my_orgs) == 1:
        form = {**form, "organization_id": my_orgs[0].id}  # 団体が 1 つなら選択済みにする
    return _tpl().TemplateResponse(
        request,
        "report_form.html",
        {
            "user": user,
            "orgs": orgs,
            "my_orgs": my_orgs,
            "show_all": show_all,
            "errors": errors,
            "form": form,
            "report": report,
            "member_org_ids": my_org_ids,
            "fiscal_year": _fiscal_year(),
        },
        status_code=status_code,
    )


async def _apply_form(request: Request, db: Session, user: User, report: ActivityReport, *, is_new: bool) -> list[str]:
    """フォーム内容を report に反映する。エラーがあればメッセージのリストを返す (DB には反映しない)。"""
    form = await request.form()
    errors: list[str] = []

    org = db.get(Organization, int(form.get("organization_id") or 0))
    if org is None or not org.is_active:
        errors.append("団体を選択してください")
    start = _parse_dt(form.get("start_at", ""), "開始日時")
    end = _parse_dt(form.get("end_at", ""), "終了日時")
    if end < start:
        errors.append("終了日時は開始日時より後にしてください")
    try:
        count = int(form.get("participants_count") or 0)
    except ValueError:
        count = 0
    if count < 1:
        errors.append("参加予定人数は1以上にしてください")
    for key, label in (
        ("content", "活動内容"),
        ("location", "活動場所・宿泊先"),
        ("leader_name", "現地責任者氏名"),
        ("leader_phone", "現地責任者携帯番号"),
        ("leader_email", "現地責任者メール"),
    ):
        if not (form.get(key) or "").strip():
            errors.append(f"{label}を入力してください")
    if form.get("requires_precheck") not in ("yes", "no"):
        errors.append("事前確認対象を選択してください")

    # 参加者名簿: 部員一覧からの選択 + 貼り付け
    selected_rows: list[RosterRow] = []
    member_ids = [int(x) for x in form.getlist("member_ids") if str(x).isdigit()]
    if member_ids and org is not None:
        if not org.is_representative(user.email):
            errors.append("部員一覧から選択できるのは、その団体の代表者・副代表者だけです")
        else:
            members = db.scalars(select(Member).where(Member.id.in_(member_ids), Member.organization_id == org.id)).all()
            selected_rows = [RosterRow(m.student_no, m.name, m.department, m.grade) for m in members]
    try:
        extra_rows = rows_from_fields(
            form.getlist("extra_student_no"), form.getlist("extra_name"), form.getlist("extra_department"), form.getlist("extra_grade")
        )
    except RosterError as e:
        extra_rows = []
        errors.append("追加の参加者の入力に誤りがあります:\n" + str(e))
    try:
        pasted_rows = parse_roster_text(form.get("roster_text", ""))
    except RosterError as e:
        pasted_rows = []
        errors.append("参加者名簿の貼り付け内容に誤りがあります:\n" + str(e))
    rows = merge(selected_rows, extra_rows, pasted_rows)

    # 添付 (サイズ検査だけ先に)
    uploads: list[tuple[AttachmentKind, str, bytes]] = []
    for field, kind in (("itinerary_files", AttachmentKind.ITINERARY), ("other_files", AttachmentKind.OTHER)):
        for f in form.getlist(field):
            if not isinstance(f, UploadFile) or not f.filename:
                continue
            data = await f.read()
            if not data:
                continue
            if len(data) > MAX_FILE_BYTES:
                errors.append(f"{f.filename} が大きすぎます (20MB まで)")
                continue
            uploads.append((kind, f.filename, data))

    if errors:
        return errors

    # --- ここから反映 ---
    report.organization = org
    report.organization_id = org.id
    report.content = form.get("content", "").strip()
    report.start_at = start
    report.end_at = end
    report.location = form.get("location", "").strip()
    report.participants_count = count
    report.leader_name = form.get("leader_name", "").strip()
    report.leader_phone = form.get("leader_phone", "").strip()
    report.leader_email = form.get("leader_email", "").strip()
    report.requires_precheck = form.get("requires_precheck") == "yes"
    report.itinerary_summary = form.get("itinerary_summary", "").strip()
    report.declared_itinerary = "itinerary" in form.getlist("declared_docs")
    report.notes_to_university = form.get("notes_to_university", "").strip()

    report.participants.clear()
    for r in rows:
        report.participants.append(Participant(student_no=r.student_no, name=r.name, department=r.department, grade=r.grade))

    if is_new:
        report.applicant_name = user.name
        report.applicant_email = user.email
        report.source = "WebForm"
        db.add(report)
        db.flush()
        report.application_no = f"ACT-{report.id:06d}"
    else:
        for att in list(report.attachments):
            if str(att.id) in form.getlist("remove_attachments"):
                storage.delete_file(att.stored_path)
                report.attachments.remove(att)

    for kind, filename, data in uploads:
        rel, _ = storage.save_attachment(report.application_no, filename, data)
        report.attachments.append(Attachment(kind=kind, original_name=filename, stored_path=rel, size_bytes=len(data)))
    return []


# ------------------------------------------------------------ 学生: 提出フォーム
@router.get("/new")
def new_form(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.can_submit:
        raise forbidden("活動届の提出は学生・団体代表者のみ行えます")
    return _render_form(request, user, db, report=None, errors=[], form={})


@router.post("/new")
async def submit(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.can_submit:
        raise forbidden("活動届の提出は学生・団体代表者のみ行えます")
    report = ActivityReport()
    errors = await _apply_form(request, db, user, report, is_new=True)
    if errors:
        form = dict(await request.form())
        form["declared_docs"] = (await request.form()).getlist("declared_docs")
        return _render_form(request, user, db, report=None, errors=errors, form=form, status_code=400)
    intake.process_submission(db, report)
    db.commit()
    return RedirectResponse(f"/reports/{report.id}/done", status_code=303)


# ------------------------------------------------------------ 学生: 差戻し後の再提出
@router.get("/{report_id}/edit")
def edit_form(report_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    report = db.get(ActivityReport, report_id)
    if report is None or not _is_owner(user, report):
        raise forbidden("この活動届を編集する権限がありません")
    if not report.can_resubmit:
        raise HTTPException(status_code=400, detail="差戻し中の活動届だけ修正・再提出できます")
    form = {
        "organization_id": report.organization_id,
        "content": report.content,
        "start_at": report.start_at.strftime("%Y-%m-%dT%H:%M"),
        "end_at": report.end_at.strftime("%Y-%m-%dT%H:%M"),
        "location": report.location,
        "participants_count": report.participants_count,
        "leader_name": report.leader_name,
        "leader_phone": report.leader_phone,
        "leader_email": report.leader_email,
        "requires_precheck": "yes" if report.requires_precheck else "no",
        "itinerary_summary": report.itinerary_summary,
        "declared_docs": ["itinerary"] if report.declared_itinerary else [],
        "notes_to_university": report.notes_to_university,
    }
    org = report.organization
    member_by_no = {}
    if org.is_representative(user.email):
        for m in db.scalars(select(Member).where(Member.organization_id == org.id, Member.fiscal_year == _fiscal_year())):
            member_by_no[m.student_no] = m.id
    form["member_ids"] = [member_by_no[p.student_no] for p in report.participants if p.student_no in member_by_no]
    form["extra_rows"] = [p for p in report.participants if p.student_no not in member_by_no]
    return _render_form(request, user, db, report=report, errors=[], form=form)


@router.post("/{report_id}/edit")
async def resubmit(report_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    report = db.get(ActivityReport, report_id)
    if report is None or not _is_owner(user, report):
        raise forbidden("この活動届を編集する権限がありません")
    if not report.can_resubmit:
        raise HTTPException(status_code=400, detail="差戻し中の活動届だけ修正・再提出できます")
    previous_remarks = report.remarks
    errors = await _apply_form(request, db, user, report, is_new=False)
    if errors:
        form = dict(await request.form())
        form["declared_docs"] = (await request.form()).getlist("declared_docs")
        return _render_form(request, user, db, report=report, errors=errors, form=form, status_code=400)
    report.revision += 1
    db.add(AuditLog(report_id=report.id, actor_email=user.email, action="再提出前の差戻し理由", detail=previous_remarks))
    intake.process_submission(db, report, resubmission=True)
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
def list_reports(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db), status: str = "", q: str = ""):
    stmt = select(ActivityReport).order_by(ActivityReport.id.desc())
    if user.can_view_all_reports:
        pass
    elif user.role == Role.ADVISOR:
        stmt = stmt.join(Organization).where(Organization.advisor_email == user.email)
    else:
        stmt = stmt.where(ActivityReport.applicant_email == user.email)
    base_stmt = stmt
    if status:
        try:
            stmt = stmt.where(ActivityReport.status == ReportStatus(status))
        except ValueError:
            pass
    if q:
        like = f"%{q}%"
        stmt = stmt.where(ActivityReport.content.like(like) | ActivityReport.application_no.like(like) | ActivityReport.location.like(like))
    reports = list(db.scalars(stmt))
    counts = {s: 0 for s in ReportStatus}
    for r in db.scalars(base_stmt):
        counts[r.status] += 1
    return _tpl().TemplateResponse(
        request,
        "report_list.html",
        {
            "user": user,
            "reports": reports,
            "statuses": list(ReportStatus),
            "status": status,
            "q": q,
            "counts": counts,
            "total": sum(counts.values()),
        },
    )


@router.get("/{report_id}")
def detail(report_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    report = db.get(ActivityReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="活動届が見つかりません")
    if not _can_view(user, report):
        raise forbidden("この活動届を閲覧する権限がありません")
    return _tpl().TemplateResponse(
        request,
        "report_detail.html",
        {
            "user": user,
            "report": report,
            "statuses": list(ReportStatus),
            "show_participants": _can_view_participants(user, report),
            "is_owner": _is_owner(user, report),
        },
    )


@router.post("/{report_id}/status")
def update_status(
    report_id: int, user: User = Depends(current_user), db: Session = Depends(get_db), status: str = Form(...), remarks: str = Form("")
):
    if not user.can_edit_reports:
        raise forbidden("状況の更新は指定職員のみ行えます")
    report = db.get(ActivityReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="活動届が見つかりません")
    try:
        new_status = ReportStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail="状況の値が不正です") from None
    intake.update_status(db, report, user, new_status, remarks.strip())
    db.commit()
    return RedirectResponse(f"/reports/{report.id}", status_code=303)


@router.get("/{report_id}/participants.csv")
def participants_csv(report_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """参加者名簿の CSV (保険実務・緊急連絡用)。指定職員・管理職のみ。"""
    if not user.can_view_rosters:
        raise forbidden("参加者名簿は指定職員・管理職のみ閲覧できます")
    report = db.get(ActivityReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="活動届が見つかりません")
    return Response(
        to_csv(report.participants),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report.application_no}_participants.csv"'},
    )


@router.get("/{report_id}/attachments/{attachment_id}")
def download(report_id: int, attachment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    att = db.get(Attachment, attachment_id)
    if att is None or att.report_id != report_id:
        raise HTTPException(status_code=404, detail="添付が見つかりません")
    if not _can_view(user, att.report):
        raise forbidden("この添付を閲覧する権限がありません")
    return FileResponse(storage.resolve(att.stored_path), filename=att.original_name)
