"""8. 自動化要件。

Power Automate のフローに相当する処理を Python で実装する。
- process_submission(): 8.1 受付後処理 (発番・団体情報取得・申請者照合・不足検査・通知)。初回提出と再提出で共通
- update_status():      8.3 結果通知 (確認済/差戻し に変更されたときだけ 1 回通知)
"""

from __future__ import annotations

from datetime import datetime

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
    if AttachmentKind.ITINERARY not in kinds:
        missing.append("行程表・活動計画書等が添付されていません")
    if not report.participants:
        missing.append("参加者名簿に参加者が登録されていません")
    return missing


def _summary(report: ActivityReport) -> str:
    org = report.organization
    return (
        f"申請番号: {report.application_no}\n団体: {org.name}\n活動内容: {report.content}\n"
        f"期間: {report.start_at:%Y-%m-%d %H:%M} ～ {report.end_at:%Y-%m-%d %H:%M}\n"
        f"場所: {report.location}\n参加予定人数: {report.participants_count} 名 (名簿 {len(report.participants)} 名)\n"
        f"現地責任者: {report.leader_name} ({report.leader_phone})\n"
    )


# ---------------------------------------------------------------- 8.1 受付後処理
def process_submission(db: Session, report: ActivityReport, *, resubmission: bool = False) -> None:
    """初回提出・再提出の両方で呼ぶ。状況・申請者確認・不足検査を決め、通知を出す。"""
    org = report.organization
    if not report.application_no:
        report.application_no = f"ACT-{report.id:06d}"  # 2. 申請番号付与
    report.org_code = org.org_code  # 3. 団体情報取得
    report.applicant_check = judge_applicant(report)  # 4. 申請者照合
    missing = find_missing(report)  # 5. 不足検査
    report.missing_items = "\n".join(missing)
    report.submitted_at = datetime.now()
    report.last_notified_status = ""  # 再提出後は改めて結果通知を出す

    tag = "再提出" if resubmission else "提出"
    subject_prefix = f"[学外活動届 {report.application_no}] {org.name}"
    applicant = report.applicant_name

    if not report.requires_precheck:
        report.status = ReportStatus.CONFIRMED
        report.last_notified_status = report.status.value
        notify.send(
            db,
            to=report.applicant_email,
            kind="receipt",
            report_id=report.id,
            subject=f"{subject_prefix} 受付完了",
            body=(
                f"{applicant} 様\n\n学外活動届を受け付けました。\n"
                + _summary(report)
                + "\n提出内容の変更または活動中止が生じた場合は、担当部署へ連絡してください。"
            ),
        )
    elif missing:
        report.status = ReportStatus.RETURNED
        report.remarks = "【自動検査】必要資料が不足しています。\n" + "\n".join(f"- {m}" for m in missing)
        report.last_notified_status = report.status.value
        notify.send(
            db,
            to=report.applicant_email,
            kind="missing",
            report_id=report.id,
            subject=f"{subject_prefix} 差戻し (必要資料の不足)",
            body=(
                f"{applicant} 様\n\n事前確認対象の活動ですが、以下の不足があるため差戻しとなりました。\n\n"
                + "\n".join(f"- {m}" for m in missing)
                + "\n\n「修正して再提出」から不足分を揃えて再提出してください。"
            ),
        )
    else:
        report.status = ReportStatus.UNCONFIRMED
        if resubmission:
            report.remarks = ""  # 前回の差戻し理由は履歴に残し、備考欄は空に戻す
        notify.send(
            db,
            to=report.applicant_email,
            kind="receipt",
            report_id=report.id,
            subject=f"{subject_prefix} 受付 (確認中)",
            body=(
                f"{applicant} 様\n\n事前確認対象の学外活動届を{'再' if resubmission else ''}受け付けました。"
                "現在、職員が内容を確認しています。\n" + _summary(report) + "\n大学からの確認結果または差戻し連絡をお待ちください。"
            ),
        )

    if report.applicant_check != ApplicantCheck.MATCH:
        notify.send(
            db,
            to=settings.staff_notify_email,
            kind="applicant_check",
            report_id=report.id,
            subject=f"{subject_prefix} 申請者確認: {report.applicant_check.value}",
            body=(
                f"申請者 {applicant} <{report.applicant_email}> は団体台帳の代表者・副代表者と一致しません。\n"
                f"判定: {report.applicant_check.value}\n内容を確認してください。"
            ),
        )

    if report.requires_precheck and not missing:  # 8. 確認依頼
        body = f"事前確認対象の学外活動届が{tag}されました。確認をお願いします。\n\n" + _summary(report)
        notify.send(
            db,
            to=settings.staff_notify_email,
            kind="staff_request",
            report_id=report.id,
            subject=f"{subject_prefix} 事前確認依頼{' (再提出)' if resubmission else ''}",
            body=body,
        )
        if org.advisor_email:
            notify.send(
                db,
                to=org.advisor_email,
                kind="advisor_share",
                report_id=report.id,
                subject=f"{subject_prefix} 事前確認対象の活動届 (共有)",
                body=body,
            )

    db.add(
        AuditLog(
            report_id=report.id,
            actor_email=report.applicant_email,
            action=f"{tag} (第{report.revision}版)",
            detail=f"状況={report.status.value} 申請者確認={report.applicant_check.value}"
            + (f"\n不足: {report.missing_items}" if missing else ""),
        )
    )


# ---------------------------------------------------------------- 8.3 結果通知
def update_status(db: Session, report: ActivityReport, actor: User, new_status: ReportStatus, remarks: str) -> bool:
    """職員による状況更新。確認済/差戻しへの変更時だけ申請者へ通知し、同一値の再保存では通知しない。

    戻り値: 通知を送ったかどうか
    """
    old_status = report.status
    report.status = new_status
    report.remarks = remarks
    report.updated_by = actor.email
    db.add(
        AuditLog(
            report_id=report.id,
            actor_email=actor.email,
            action="状況更新",
            detail=f"{old_status.value} → {new_status.value}" + (f"\n備考: {remarks}" if remarks.strip() else ""),
        )
    )

    should_notify = new_status in (ReportStatus.CONFIRMED, ReportStatus.RETURNED) and report.last_notified_status != new_status.value
    if not should_notify:
        return False

    subject_prefix = f"[学外活動届 {report.application_no}] {report.organization.name}"
    if new_status == ReportStatus.CONFIRMED:
        body = f"{report.applicant_name} 様\n\n提出された学外活動届は確認済となりました。\n申請番号: {report.application_no}\n"
        if remarks.strip():
            body += f"\n【大学からの指示・連絡】\n{remarks}\n"
        notify.send(db, to=report.applicant_email, kind="result", report_id=report.id, subject=f"{subject_prefix} 確認済", body=body)
    else:
        body = (
            f"{report.applicant_name} 様\n\n提出された学外活動届は差戻しとなりました。\n申請番号: {report.application_no}\n\n"
            f"【差戻し理由】\n{remarks or '(理由未記入)'}\n\n「修正して再提出」から内容を修正のうえ再提出してください。"
        )
        notify.send(db, to=report.applicant_email, kind="result", report_id=report.id, subject=f"{subject_prefix} 差戻し", body=body)
    report.last_notified_status = new_status.value
    return True
