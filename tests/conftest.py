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


def submit_report(client, *, org_id: int, precheck: bool, files: dict | None = None, declared=(), **overrides):
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
        "notes_to_university": "",
    }
    data.update(overrides)
    uploads = []
    for field, items in (files or {}).items():
        for name, content in items:
            uploads.append((field, (name, content, "application/octet-stream")))
    r = client.post("/reports/new", data=data, files=uploads or None, follow_redirects=False)
    assert r.status_code == 303, r.text
    report_id = int(r.headers["location"].split("/")[2])
    return report_id
