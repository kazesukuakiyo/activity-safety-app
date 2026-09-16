"""ローカル検証用の初期データ (団体台帳) を投入する。

使い方:  python seed.py
何度実行しても重複登録はしない。
"""
from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Organization

ORGS = [
    # 団体名, 団体ID, 代表者, 副代表者, 顧問, 有効
    ("硬式テニス部", "ORG-0001", "tanaka@example.ac.jp", "", "advisor.tennis@example.ac.jp", True),
    ("登山部", "ORG-0002", "yamada@example.ac.jp", "suzuki@example.ac.jp", "advisor.alpine@example.ac.jp", True),
    ("軽音楽サークル", "ORG-0003", "", "", "advisor.music@example.ac.jp", True),   # 代表者未登録 → 照合不可
    ("旧・写真部 (休止)", "ORG-0004", "old@example.ac.jp", "", "", False),
]


def main() -> None:
    init_db()
    with SessionLocal() as db:
        added = 0
        for name, code, rep, vice, advisor, active in ORGS:
            if db.scalar(select(Organization).where(Organization.org_code == code)):
                continue
            db.add(Organization(name=name, org_code=code, rep_email=rep, vice_rep_email=vice, advisor_email=advisor, is_active=active))
            added += 1
        db.commit()
    print(f"団体台帳: {added} 件追加しました (既存は保持)")


if __name__ == "__main__":
    main()
