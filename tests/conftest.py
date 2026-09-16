"""テスト用の共通設定。一時ディレクトリに SQLite と保管先を作り、本物のデータを汚さない。"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# app を import する前に、テスト専用の一時ディレクトリを設定する
_TMP = Path(tempfile.mkdtemp(prefix="activity-safety-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["DATA_DIR"] = str(_TMP)
os.environ["AUTH_MODE"] = "dev"
os.environ["STAFF_NOTIFY_EMAIL"] = "staff@example.ac.jp"


@pytest.fixture(scope="session")
def app_env():
    import seed

    seed.main()
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture()
def client(app_env):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(app_env):
    from app.database import SessionLocal

    with SessionLocal() as s:
        yield s


def login(client, email: str):
    r = client.post("/auth/login", data={"email": email, "next": "/"}, follow_redirects=False)
    assert r.status_code == 303
    return client


ROSTER_TEXT = "2023001\t田中 太郎\t工学部\t3\n2024001\t中村 健\t経済学部\t2\n"


def report_data(*, org_id: int, precheck: bool, roster: str = "", declared=(), **overrides) -> dict:
    data = {
        "organization_id": str(org_id),
        "content": "テスト大会への参加",
        "start_at": "2026-10-10T08:00",
        "end_at": "2026-10-11T18:00",
        "location": "〇〇県総合運動公園",
        "participants_count": "12",
        "leader_name": "現地 太郎",
        "leader_phone": "090-0000-0000",
        "leader_email": "leader@example.ac.jp",
        "requires_precheck": "yes" if precheck else "no",
        "itinerary_summary": "1日目移動、2日目試合" if precheck else "",
        "declared_docs": list(declared),
        "roster_text": roster,
        "notes_to_university": "",
    }
    data.update(overrides)
    return data


ITINERARY_FILE = [("itinerary_files", ("itinerary.pdf", b"%PDF itinerary", "application/pdf"))]


def submit_report(client, *, org_id: int, precheck: bool, roster: str = "", itinerary_file: bool = False, declared=(), **overrides):
    data = report_data(org_id=org_id, precheck=precheck, roster=roster, declared=declared, **overrides)
    r = client.post("/reports/new", data=data, files=ITINERARY_FILE if itinerary_file else None, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].split("/")[2])


def submit_full(client, *, org_id: int):
    """事前確認対象を必要資料つきで提出する"""
    return submit_report(client, org_id=org_id, precheck=True, roster=ROSTER_TEXT, itinerary_file=True, declared=("itinerary",))
