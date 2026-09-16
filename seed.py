"""ローカル検証用の初期データ (団体台帳・年度部員名簿) を投入する。

使い方:  python seed.py
何度実行しても重複登録はしない。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Member, Organization

ORGS = [
    # 団体名, 団体ID, 代表者, 副代表者, 顧問, 有効
    ("硬式テニス部", "ORG-0001", "tanaka@example.ac.jp", "", "advisor.tennis@example.ac.jp", True),
    ("登山部", "ORG-0002", "yamada@example.ac.jp", "suzuki@example.ac.jp", "advisor.alpine@example.ac.jp", True),
    ("軽音楽サークル", "ORG-0003", "", "", "advisor.music@example.ac.jp", True),  # 代表者未登録 → 照合不可
    ("旧・写真部 (休止)", "ORG-0004", "old@example.ac.jp", "", "", False),
]

# 年度部員名簿のサンプル (テニス部のみ)。学籍番号, 氏名, 所属, 学年
MEMBERS = {
    "ORG-0001": [
        ("2023001", "田中 太郎", "工学部", "3"),
        ("2023002", "小林 美咲", "文学部", "3"),
        ("2024001", "中村 健", "経済学部", "2"),
        ("2024002", "加藤 結衣", "理学部", "2"),
        ("2025001", "松本 大輔", "工学部", "1"),
        ("2025002", "井上 さくら", "教育学部", "1"),
    ],
}


def fiscal_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def main() -> None:
    init_db()
    fy = fiscal_year()
    with SessionLocal() as db:
        added = 0
        for name, code, rep, vice, advisor, active in ORGS:
            if db.scalar(select(Organization).where(Organization.org_code == code)):
                continue
            db.add(Organization(name=name, org_code=code, rep_email=rep, vice_rep_email=vice, advisor_email=advisor, is_active=active))
            added += 1
        db.flush()
        members_added = 0
        for code, rows in MEMBERS.items():
            org = db.scalar(select(Organization).where(Organization.org_code == code))
            for student_no, name, dept, grade in rows:
                exists = db.scalar(
                    select(Member).where(Member.organization_id == org.id, Member.fiscal_year == fy, Member.student_no == student_no)
                )
                if exists:
                    continue
                db.add(
                    Member(
                        organization_id=org.id,
                        fiscal_year=fy,
                        student_no=student_no,
                        name=name,
                        department=dept,
                        grade=grade,
                        registered_by="seed",
                    )
                )
                members_added += 1
        db.commit()
    print(f"団体台帳: {added} 件追加、{fy} 年度部員名簿: {members_added} 名追加 (既存は保持)")


if __name__ == "__main__":
    main()
