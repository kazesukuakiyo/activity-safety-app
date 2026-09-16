"""8. 自動化要件。

Power Automate のフローに相当する処理を Python で実装する。
- process_new_report(): 8.1 受付後処理 (発番・団体情報取得・申請者照合・不足検査・通知)
- update_status():      8.3 結果通知 (確認済/差戻し に変更されたときだけ 1 回通知)
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..auth.base import User
from ..config import settings
from ..models import ActivityReport, ApplicantCheck, AttachmentKind, AuditLog, ReportStatus
from . import notify


# ---------------------------------------------------------------- 8.2 判定ルール
def judge_applicant(report: ActivityReport) -> ApplicantCheck:
    org = report.organization
    rep = (org.rep_email or "").strip().lower()
    vice = (org.vice_rep_email or "").strip().lower()
    applicant = (report.applicant_email or "").strip().lower()
    if not rep and not vice:
        return ApplicantCheck.UNVERIFIABLE
    if applicant and applicant in (rep, vice):
        return ApplicantCheck.MATCH
    return ApplicantCheck.NEEDS_REVIEW


def find_missing(report: ActivityReport) -> list[str]:
    """8.1-5 不足検査。事前確認対象のみ検査する。"""
    if not report.requires_precheck:
        return []
    missing: list[str] = []
    kinds = {a.kind for a in report.attachments}
    if not report.itinerary_summary.strip():
        missing.append("行程等の概要が入力されていません")
    if not report.declared_itinerary:
        missing.append("添付書類確認で「行程等」が選択されていません")
    if not report.declared_roster:
        missing.append("添付書類確認で「参加者名簿」が選択されていません")
    if AttachmentKind.ITINERARY not in kinds:
        missing.append("行程表・活動計画書等が添付されていません")
    if AttachmentKind.ROSTER not in kinds:
        missing.append("参加者名簿が添付されていません")
    return missing


# ---------------------------------------------------------------- 8.1 受付後処理
def process_new_report(db: Session, report: ActivityReport) -> None:
    # 2. 申請番号付与
    report.application_no = f"ACT-{report.id:06d}"
    # 3. 団体情報取得
    org = report.organization
    report.org_code = org.org_code
    # 4. 申請者照合
    report.applicant_check = judge_applicant(report)
    # 5. 不足検査
    missing = find_missing(report)
    report.missing_items = "\n".join(missing)

    subject_prefix = f"[学外活動届 {report.application_no}] {org.name}"

    if not report.requires_precheck:
        # 通常活動: 受付完了
        report.status = ReportStatus.CONFIRMED
        report.last_notified_status = report.status.value
        notify.send(
            db, to=report.applicant_email, kind="receipt", report_id=report.id,
            subject=f"{subject_prefix} 受付完了",
            body=(
                f"{report.applicant_name} 様\n\n学外活動届を受け付けました。\n"
                f"申請番号: {report.application_no}\n活動内容: {report.content}\n"
                f"期間: {report.start_at:%Y-%m-%d %H:%M} ～ {report.end_at:%Y-%m-%d %H:%M}\n\n"
                "提出内容の変更または活動中止が生じた場合は、担当部署へ連絡してください。"
            ),
        )
    elif missing:
        # 対象活動・資料不足: 差戻し
        report.status = ReportStatus.RETURNED
        report.remarks = "【自動検査】必要資料が不足しています。\n" + "\n".join(f"- {m}" for m in missing)
        report.last_notified_status = report.status.value
        notify.send(
            db, to=report.applicant_email, kind="missing", report_id=report.id,
            subject=f"{subject_prefix} 差戻し (必要資料の不足)",
            body=(
                f"{report.applicant_name} 様\n\n事前確認対象の活動ですが、以下の不足があるため差戻しとなりました。\n\n"
                + "\n".join(f"- {m}" for m in missing)
                + "\n\n不足分を揃えて再提出してください。"
            ),
        )
    else:
        # 対象活動・資料あり: 確認中 → 職員へ確認依頼
        report.status = ReportStatus.UNCONFIRMED
        notify.send(
            db, to=report.applicant_email, kind="receipt", report_id=report.id,
            subject=f"{subject_prefix} 受付 (確認中)",
            body=(
                f"{report.applicant_name} 様\n\n事前確認対象の学外活動届を受け付けました。現在、職員が内容を確認しています。\n"
                f"申請番号: {report.application_no}\n\n大学からの確認結果または差戻し連絡をお待ちください。"
            ),
        )

    # 申請者照合が「要確認」「照合不可」なら職員へ通知
    if report.applicant_check != ApplicantCheck.MATCH:
        notify.send(
            db, to=settings.staff_notify_email, kind="applicant_check", report_id=report.id,
            subject=f"{subject_prefix} 申請者確認: {report.applicant_check.value}",
            body=(
                f"申請者 {report.applicant_name} <{report.applicant_email}> は団体台帳の代表者・副代表者と一致しません。\n"
                f"判定: {report.applicant_check.value}\n内容を確認してください。"
            ),
        )

    # 8. 確認依頼 (対象活動・資料あり)
    if report.requires_precheck and not missing:
        body = (
            f"事前確認対象の学外活動届が提出されました。確認をお願いします。\n\n"
            f"申請番号: {report.application_no}\n団体: {org.name}\n活動内容: {report.content}\n"
            f"期間: {report.start_at:%Y-%m-%d %H:%M} ～ {report.end_at:%Y-%m-%d %H:%M}\n"
            f"場所: {report.location}\n現地責任者: {report.leader_name} ({report.leader_phone})\n"
        )
        notify.send(db, to=settings.staff_notify_email, kind="staff_request", report_id=report.id,
                    subject=f"{subject_prefix} 事前確認依頼", body=body)
        if org.advisor_email:
            notify.send(db, to=org.advisor_email, kind="advisor_share", report_id=report.id,
                        subject=f"{subject_prefix} 事前確認対象の活動届 (共有)", body=body)

    db.add(AuditLog(report_id=report.id, actor_email="system", action="受付後処理",
                    detail=f"状況={report.status.value} 申請者確認={report.applicant_check.value}"))


# ---------------------------------------------------------------- 8.3 結果通知
def update_status(db: Session, report: ActivityReport, actor: User, new_status: ReportStatus, remarks: str) -> bool:
    """職員による状況更新。確認済/差戻しへの変更時だけ申請者へ通知し、同一値の再保存では通知しない。

    戻り値: 通知を送ったかどうか
    """
    old_status = report.status
    report.status = new_status
    report.remarks = remarks
    report.updated_by = actor.email
    db.add(AuditLog(report_id=report.id, actor_email=actor.email, action="状況更新",
                    detail=f"{old_status.value} → {new_status.value}"))

    should_notify = (
        new_status in (ReportStatus.CONFIRMED, ReportStatus.RETURNED)
        and report.last_notified_status != new_status.value
    )
    if not should_notify:
        return False

    org = report.organization
    subject_prefix = f"[学外活動届 {report.application_no}] {org.name}"
    if new_status == ReportStatus.CONFIRMED:
        body = (
            f"{report.applicant_name} 様\n\n提出された学外活動届は確認済となりました。\n申請番号: {report.application_no}\n"
        )
        if remarks.strip():
            body += f"\n【大学からの指示・連絡】\n{remarks}\n"
        notify.send(db, to=report.applicant_email, kind="result", report_id=report.id,
                    subject=f"{subject_prefix} 確認済", body=body)
    else:
        body = (
            f"{report.applicant_name} 様\n\n提出された学外活動届は差戻しとなりました。\n申請番号: {report.application_no}\n\n"
            f"【差戻し理由】\n{remarks or '(理由未記入)'}\n\n内容を修正のうえ再提出してください。"
        )
        notify.send(db, to=report.applicant_email, kind="result", report_id=report.id,
                    subject=f"{subject_prefix} 差戻し", body=body)
    report.last_notified_status = new_status.value
    return True
