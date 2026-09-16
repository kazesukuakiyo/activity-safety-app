"""DB モデル。要件定義書 v3.0 の「活動届リスト」「団体台帳」「名簿保管先」に対応する。"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class ApplicantCheck(str, enum.Enum):
    """6.2 申請者確認"""

    MATCH = "一致"
    NEEDS_REVIEW = "要確認"
    UNVERIFIABLE = "照合不可"


class ReportStatus(str, enum.Enum):
    """6.2 状況"""

    UNCONFIRMED = "未確認"
    CONFIRMED = "確認済"
    RETURNED = "差戻し"
    CANCELLED = "中止"
    COMPLETED = "完了"


class AttachmentKind(str, enum.Enum):
    """添付振分け用の種別"""

    ITINERARY = "行程等"      # 行程表・活動計画書・大会要項 → 活動資料
    ROSTER = "参加者名簿"     # → 個人情報管理サイト (限定保管先)
    OTHER = "その他"          # → 活動資料


class Organization(Base):
    """7.2 団体台帳"""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)          # 団体名 (学生向け表示名)
    org_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 団体ID (不変キー)
    rep_email: Mapped[str] = mapped_column(String(200), default="")         # 代表者メール
    vice_rep_email: Mapped[str] = mapped_column(String(200), default="")    # 副代表者メール (任意)
    advisor_email: Mapped[str] = mapped_column(String(200), default="")     # 顧問メール
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)          # 有効フラグ

    reports: Mapped[list[ActivityReport]] = relationship(back_populates="organization")


class ActivityReport(Base):
    """6.1 / 6.2 活動届"""

    __tablename__ = "activity_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- 6.1 学生が入力する項目 ---
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)                 # 活動内容
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)       # 開始日時
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)         # 終了日時
    location: Mapped[str] = mapped_column(Text, nullable=False)                # 活動場所・宿泊先
    participants_count: Mapped[int] = mapped_column(Integer, nullable=False)   # 参加予定人数
    leader_name: Mapped[str] = mapped_column(String(100), nullable=False)      # 現地責任者氏名
    leader_phone: Mapped[str] = mapped_column(String(50), nullable=False)      # 現地責任者携帯番号 (文字列)
    leader_email: Mapped[str] = mapped_column(String(200), nullable=False)     # 現地責任者メール
    requires_precheck: Mapped[bool] = mapped_column(Boolean, nullable=False)   # 事前確認対象
    itinerary_summary: Mapped[str] = mapped_column(Text, default="")           # 行程等の概要
    declared_itinerary: Mapped[bool] = mapped_column(Boolean, default=False)   # 添付書類確認: 行程等
    declared_roster: Mapped[bool] = mapped_column(Boolean, default=False)      # 添付書類確認: 参加者名簿
    notes_to_university: Mapped[str] = mapped_column(Text, default="")         # 大学への連絡事項

    # --- 6.2 内部管理項目 ---
    application_no: Mapped[str] = mapped_column(String(30), unique=True, default="")  # 申請番号 ACT-{id}
    org_code: Mapped[str] = mapped_column(String(50), default="")               # 団体ID (台帳から自動取得)
    applicant_name: Mapped[str] = mapped_column(String(100), default="")
    applicant_email: Mapped[str] = mapped_column(String(200), default="")
    applicant_check: Mapped[ApplicantCheck] = mapped_column(Enum(ApplicantCheck), default=ApplicantCheck.NEEDS_REVIEW)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.UNCONFIRMED)
    remarks: Mapped[str] = mapped_column(Text, default="")                      # 備考 (差戻し理由など)
    source: Mapped[str] = mapped_column(String(50), default="WebForm")          # 作成元
    missing_items: Mapped[str] = mapped_column(Text, default="")                # 不足検査の結果 (改行区切り)
    last_notified_status: Mapped[str] = mapped_column(String(20), default="")   # 重複通知抑止用

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by: Mapped[str] = mapped_column(String(200), default="")

    organization: Mapped[Organization] = relationship(back_populates="reports")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="report", cascade="all, delete-orphan")

    @property
    def is_precheck_target(self) -> bool:
        return self.requires_precheck


class Attachment(Base):
    """活動届の添付ファイル。種別に応じて保管先を振り分ける (8.1-6)。"""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("activity_reports.id"), nullable=False)
    kind: Mapped[AttachmentKind] = mapped_column(Enum(AttachmentKind), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)   # 保管先の相対パス
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)      # True = 限定保管先
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    report: Mapped[ActivityReport] = relationship(back_populates="attachments")


class AnnualRoster(Base):
    """3.2 年度部員名簿 (活動届とは別業務・別保管単位)"""

    __tablename__ = "annual_rosters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    submitted_by_email: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    organization: Mapped[Organization] = relationship()


class Notification(Base):
    """通知ログ。ローカル検証ではメール送信の代わりに DB に記録し「送信箱」画面で確認する。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("activity_reports.id"), nullable=True)
    to_email: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(50), default="")   # receipt / staff_request / result / missing など
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AuditLog(Base):
    """9. 監査性: 状況・備考の更新履歴を保持する。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("activity_reports.id"), nullable=False)
    actor_email: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
