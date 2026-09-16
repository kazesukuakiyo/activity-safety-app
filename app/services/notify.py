"""通知。ローカル検証では DB (notifications テーブル) に記録し、/notifications 画面で確認する。

本番でメール送信にする場合は send() の中を SMTP / Microsoft Graph 送信に差し替える。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Notification


def send(db: Session, *, to: str, subject: str, body: str, kind: str, report_id: int | None = None) -> Notification:
    n = Notification(report_id=report_id, to_email=to, subject=subject, body=body, kind=kind)
    db.add(n)
    db.flush()
    print(f"[通知] to={to} kind={kind} subject={subject}")
    return n
