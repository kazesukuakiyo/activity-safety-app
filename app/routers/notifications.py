"""通知の送信箱 (ローカル検証用)。本番ではメールになる通知をここで確認する。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.base import User, current_user
from ..database import get_db
from ..models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def outbox(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..main import templates

    stmt = select(Notification).order_by(Notification.id.desc())
    if not user.can_view_all_reports:
        # 学生・顧問は自分宛ての通知だけ見える
        stmt = stmt.where(Notification.to_email == user.email)
    items = list(db.scalars(stmt.limit(200)))
    return templates.TemplateResponse(request, "outbox.html", {"user": user, "items": items})
