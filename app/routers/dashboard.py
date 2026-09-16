"""職員ダッシュボード: 有事の初動画面。

「いま学外にいる団体」「今週の予定」「未確認・差戻し中」を一画面にまとめ、
現地責任者の連絡先と参加者数をすぐ引けるようにする。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.base import User, current_user, forbidden
from ..database import get_db
from ..models import ActivityReport, ApplicantCheck, ReportStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ACTIVE = (ReportStatus.UNCONFIRMED, ReportStatus.CONFIRMED, ReportStatus.COMPLETED)


@router.get("")
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
              q: str = "", on: str = ""):
    from ..main import templates

    if not user.can_view_all_reports:
        raise forbidden("ダッシュボードは職員・管理職のみ閲覧できます")

    now = datetime.now()
    week_end = now + timedelta(days=7)

    # 検索: 場所・活動内容・団体名 + 指定日に実施中のもの
    search_results = None
    if q or on:
        stmt = select(ActivityReport).where(ActivityReport.status.in_(ACTIVE))
        if q:
            like = f"%{q}%"
            stmt = stmt.where(ActivityReport.location.like(like) | ActivityReport.content.like(like)
                              | ActivityReport.application_no.like(like) | ActivityReport.leader_name.like(like))
        if on:
            try:
                day = datetime.fromisoformat(on)
                stmt = stmt.where(ActivityReport.start_at < day + timedelta(days=1), ActivityReport.end_at >= day)
            except ValueError:
                pass
        search_results = list(db.scalars(stmt.order_by(ActivityReport.start_at)))
        if q:
            search_results = [r for r in search_results if q in r.location or q in r.content or q in r.application_no
                              or q in r.leader_name or q in r.organization.name]

    ongoing = list(db.scalars(select(ActivityReport).where(
        ActivityReport.status.in_(ACTIVE), ActivityReport.start_at <= now, ActivityReport.end_at >= now,
    ).order_by(ActivityReport.end_at)))
    upcoming = list(db.scalars(select(ActivityReport).where(
        ActivityReport.status.in_(ACTIVE), ActivityReport.start_at > now, ActivityReport.start_at <= week_end,
    ).order_by(ActivityReport.start_at)))
    unconfirmed = list(db.scalars(select(ActivityReport).where(ActivityReport.status == ReportStatus.UNCONFIRMED).order_by(ActivityReport.start_at)))
    returned = list(db.scalars(select(ActivityReport).where(ActivityReport.status == ReportStatus.RETURNED).order_by(ActivityReport.submitted_at.desc())))
    needs_review = list(db.scalars(select(ActivityReport).where(
        ActivityReport.applicant_check != ApplicantCheck.MATCH, ActivityReport.status.in_(ACTIVE),
    ).order_by(ActivityReport.id.desc())))

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user, "now": now, "ongoing": ongoing, "upcoming": upcoming, "unconfirmed": unconfirmed,
        "returned": returned, "needs_review": needs_review, "q": q, "on": on, "search_results": search_results,
    })
