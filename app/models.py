"""DB モデル。要件定義書 v3.0 の「活動届リスト」「団体台帳」「名簿保管先」に対応する。

名簿 (年度部員名簿・活動参加者名簿) はファイルではなく、
「学籍番号・氏名・所属・学年」の 4 列だけを持つ表として保持する。
入力欄がこの 4 列しか無いので、病歴・保護者連絡先などの要配慮情報は物理的に登録できない。
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class ApplicantCheck(enum.StrEnum):
    """6.2 申請者確認"""

    MATCH = "一致"
    NEEDS_REVIEW = "要確認"
    UNVERIFIABLE = "照合不可"


class ReportStatus(enum.StrEnum):
    """6.2 状況"""

    UNCONFIRMED = "未確認"
    CONFIRMED = "確認済"
    RETURNED = "差戻し"
    CANCELLED = "中止"
    COMPLETED = "完了"


class AttachmentKind(enum.StrEnum):
    """添付ファイルの種別 (名簿はファイルではなく表で持つので種別に含めない)"""

    ITINERARY = "行程等"  # 行程表・活動計画書・大会要項
    OTHER = "その他"


class Organization(Base):
    """7.2 団体台帳"""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # 団体名 (学生向け表示名)
    org_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 団体ID (不変キー)
    rep_email: Mapped[str] = mapped_column(String(200), default="")  # 代表者メール
    vice_rep_email: Mapped[str] = mapped_column(String(200), default="")  # 副代表者メール (任意)
    advisor_email: Mapped[str] = mapped_column(String(200), default="")  # 顧問メール
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 有効フラグ

    reports: Mapped[list[ActivityReport]] = relationship(back_populates="organization")
    members: Mapped[list[Member]] = relationship(back_populates="organization", cascade="all, delete-orphan")

    def is_representative(self, email: str) -> bool:
        e = (email or "").strip().lower()
        return bool(e) and e in ((self.rep_email or "").lower(), (self.vice_rep_email or "").lower())


class Member(Base):
    """3.2 年度部員名簿の 1 行。団体 × 年度ごとに保持する。"""

    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("organization_id", "fiscal_year", "student_no", name="uq_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    student_no: Mapped[str] = mapped_column(String(30), nullable=False)  # 学籍番号
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 氏名
    department: Mapped[str] = mapped_column(String(100), nullable=False)  # 所属
    grade: Mapped[str] = mapped_column(String(10), nullable=False)  # 学年
    registered_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    organization: Mapped[Organization] = relationship(back_populates="members")


class ActivityReport(Base):
    """6.1 / 6.2 活動届"""

    __tablename__ = "activity_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- 6.1 学生が入力する項目 ---
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 活動内容
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 開始日時
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 終了日時
    location: Mapped[str] = mapped_column(Text, nullable=False)  # 活動場所・宿泊先
    participants_count: Mapped[int] = mapped_column(Integer, nullable=False)  # 参加予定人数 (教職員等を含む合計)
    leader_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 現地責任者氏名
    leader_phone: Mapped[str] = mapped_column(String(50), nullable=False)  # 現地責任者携帯番号 (文字列)
    leader_email: Mapped[str] = mapped_column(String(200), nullable=False)  # 現地責任者メール
    requires_precheck: Mapped[bool] = mapped_column(Boolean, nullable=False)  # 事前確認対象
    itinerary_summary: Mapped[str] = mapped_column(Text, default="")  # 行程等の概要
    declared_itinerary: Mapped[bool] = mapped_column(Boolean, default=False)  # 添付書類確認: 行程等
    notes_to_university: Mapped[str] = mapped_column(Text, default="")  # 大学への連絡事項

    # --- 6.2 内部管理項目 ---
    application_no: Mapped[str] = mapped_column(String(30), unique=True, default="")  # 申請番号 ACT-{id}
    org_code: Mapped[str] = mapped_column(String(50), default="")  # 団体ID (台帳から自動取得)
    applicant_name: Mapped[str] = mapped_column(String(100), default="")
    applicant_email: Mapped[str] = mapped_column(String(200), default="")
    applicant_check: Mapped[ApplicantCheck] = mapped_column(Enum(ApplicantCheck), default=ApplicantCheck.NEEDS_REVIEW)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.UNCONFIRMED)
    remarks: Mapped[str] = mapped_column(Text, default="")  # 備考 (差戻し理由など)
    source: Mapped[str] = mapped_column(String(50), default="WebForm")  # 作成元
    missing_items: Mapped[str] = mapped_column(Text, default="")  # 不足検査の結果 (改行区切り)
    last_notified_status: Mapped[str] = mapped_column(String(20), default="")  # 重複通知抑止用
    revision: Mapped[int] = mapped_column(Integer, default=1)  # 提出回数 (再提出で +1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)  # 最終提出 (再提出) 日時
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by: Mapped[str] = mapped_column(String(200), default="")

    organization: Mapped[Organization] = relationship(back_populates="reports")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="report", cascade="all, delete-orphan")
    participants: Mapped[list[Participant]] = relationship(back_populates="report", cascade="all, delete-orphan", order_by="Participant.id")
    logs: Mapped[list[AuditLog]] = relationship(back_populates="report", cascade="all, delete-orphan", order_by="AuditLog.id")

    @property
    def can_resubmit(self) -> bool:
        return self.status == ReportStatus.RETURNED

    @property
    def is_active_status(self) -> bool:
        """有事の初動で対象にすべき届 (中止・差戻しは除く)"""
        return self.status in (ReportStatus.UNCONFIRMED, ReportStatus.CONFIRMED, ReportStatus.COMPLETED)


class Participant(Base):
    """活動参加者名簿の 1 行。活動届ごとに保持し、閲覧は指定職員・管理職・提出者本人に限定する。"""

    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("activity_reports.id"), nullable=False)
    student_no: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    grade: Mapped[str] = mapped_column(String(10), nullable=False)

    report: Mapped[ActivityReport] = relationship(back_populates="participants")


class Attachment(Base):
    """活動届の添付ファイル (行程表・大会要項など)。data/activity_docs/ に保存する。"""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("activity_reports.id"), nullable=False)
    kind: Mapped[AttachmentKind] = mapped_column(Enum(AttachmentKind), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)  # 保管先の相対パス
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    report: Mapped[ActivityReport] = relationship(back_populates="attachments")


class Notification(Base):
    """通知ログ。ローカル検証ではメール送信の代わりに DB に記録し「送信箱」画面で確認する。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("activity_reports.id"), nullable=True)
    to_email: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(50), default="")  # receipt / staff_request / result / missing など
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AuditLog(Base):
    """9. 監査性: 提出・再提出・状況更新の履歴を保持する。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("activity_reports.id"), nullable=False)
    actor_email: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    report: Mapped[ActivityReport] = relationship(back_populates="logs")
