"""12. 受入要件・テスト の各シナリオを自動テストにしたもの。

実行:  pytest -v
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import ActivityReport, Attachment, Notification, Organization

from .conftest import login, submit_report

TENNIS_REP = "tanaka@example.ac.jp"      # 硬式テニス部の代表
ALPINE_VICE = "suzuki@example.ac.jp"     # 登山部の副代表
OTHER_STUDENT = "sato@example.ac.jp"     # どの団体の代表でもない
STAFF = "staff@example.ac.jp"
MANAGER = "manager@example.ac.jp"
ADVISOR = "advisor.tennis@example.ac.jp"
SYSADMIN = "sysadmin@example.ac.jp"


def org_id(db, code: str) -> int:
    return db.scalar(select(Organization).where(Organization.org_code == code)).id


def notifications_for(db, report_id: int, kind: str | None = None) -> list[Notification]:
    stmt = select(Notification).where(Notification.report_id == report_id)
    if kind:
        stmt = stmt.where(Notification.kind == kind)
    return list(db.scalars(stmt))


def get_report(db, report_id: int) -> ActivityReport:
    db.expire_all()
    return db.get(ActivityReport, report_id)


FULL_FILES = {
    "itinerary_files": [("itinerary.pdf", b"%PDF itinerary")],
    "roster_files": [("roster.xlsx", b"roster bytes")],
}


# シナリオ1: 通常活動を提出 → 直接登録され、受付完了通知が届く
def test_1_normal_activity_receipt(client, db):
    login(client, TENNIS_REP)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=False)
    r = get_report(db, rid)
    assert r.application_no == f"ACT-{rid:06d}"
    assert r.status.value == "確認済"
    assert r.org_code == "ORG-0001"
    receipts = notifications_for(db, rid, "receipt")
    assert len(receipts) == 1 and receipts[0].to_email == TENNIS_REP and "受付完了" in receipts[0].subject


# シナリオ2: 対象活動を必要資料付きで提出 → 資料が適切な保管先へ、確認依頼が届く
def test_2_precheck_with_documents(client, db, app_env):
    login(client, TENNIS_REP)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=True, files=FULL_FILES, declared=("itinerary", "roster"))
    r = get_report(db, rid)
    assert r.status.value == "未確認"
    assert r.missing_items == ""
    atts = {a.kind.value: a for a in r.attachments}
    assert atts["行程等"].stored_path.startswith("activity_docs/") and not atts["行程等"].is_restricted
    assert atts["参加者名簿"].stored_path.startswith("personal_info_vault/") and atts["参加者名簿"].is_restricted
    assert (app_env / atts["参加者名簿"].stored_path).exists()
    staff_req = notifications_for(db, rid, "staff_request")
    assert len(staff_req) == 1 and staff_req[0].to_email == STAFF
    assert len(notifications_for(db, rid, "advisor_share")) == 1  # 顧問へ共有
    assert "確認中" in notifications_for(db, rid, "receipt")[0].subject


# シナリオ3: 対象活動を資料不足で提出 → 差戻し、不足内容の通知
def test_3_precheck_missing_documents(client, db):
    login(client, TENNIS_REP)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=True)  # 添付なし・自己申告なし
    r = get_report(db, rid)
    assert r.status.value == "差戻し"
    assert "参加者名簿が添付されていません" in r.missing_items
    assert "行程表・活動計画書等が添付されていません" in r.missing_items
    missing = notifications_for(db, rid, "missing")
    assert len(missing) == 1 and "不足" in missing[0].subject and "参加者名簿" in missing[0].body
    assert notifications_for(db, rid, "staff_request") == []  # 職員への確認依頼は出さない


# シナリオ4: 登録代表者が自団体を選択 → 申請者確認が一致
def test_4_applicant_match(client, db):
    login(client, ALPINE_VICE)  # 副代表でも一致
    rid = submit_report(client, org_id=org_id(db, "ORG-0002"), precheck=False)
    assert get_report(db, rid).applicant_check.value == "一致"
    assert notifications_for(db, rid, "applicant_check") == []


# シナリオ5: 別団体または未登録者が提出 → 要確認 / 照合不可 となり職員が把握できる
def test_5_applicant_mismatch_and_unverifiable(client, db):
    login(client, OTHER_STUDENT)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=False)
    assert get_report(db, rid).applicant_check.value == "要確認"
    alerts = notifications_for(db, rid, "applicant_check")
    assert len(alerts) == 1 and alerts[0].to_email == STAFF

    rid2 = submit_report(client, org_id=org_id(db, "ORG-0003"), precheck=False)  # 代表者未登録の団体
    assert get_report(db, rid2).applicant_check.value == "照合不可"
    assert len(notifications_for(db, rid2, "applicant_check")) == 1


# シナリオ6: 職員が確認済へ変更 → 申請者へ結果通知が 1 回届く (再保存で重複しない)
def test_6_staff_confirms_once(client, db):
    login(client, TENNIS_REP)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=True, files=FULL_FILES, declared=("itinerary", "roster"))
    login(client, STAFF)
    for _ in range(3):  # 同じ値で3回保存
        r = client.post(f"/reports/{rid}/status", data={"status": "確認済", "remarks": "帰着後に電話連絡すること"}, follow_redirects=False)
        assert r.status_code == 303
    results = notifications_for(db, rid, "result")
    assert len(results) == 1
    assert results[0].to_email == TENNIS_REP and "確認済" in results[0].subject and "帰着後" in results[0].body
    assert get_report(db, rid).status.value == "確認済"


# シナリオ7: 職員が差戻しへ変更 → 備考の理由を含む通知
def test_7_staff_returns_with_reason(client, db):
    login(client, TENNIS_REP)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=True, files=FULL_FILES, declared=("itinerary", "roster"))
    login(client, STAFF)
    client.post(f"/reports/{rid}/status", data={"status": "差戻し", "remarks": "行程表に宿泊先の住所を追記してください"}, follow_redirects=False)
    results = notifications_for(db, rid, "result")
    assert len(results) == 1 and "差戻し" in results[0].subject
    assert "宿泊先の住所" in results[0].body


# シナリオ8: 学生アカウントで一覧・他人の届・名簿にアクセス → 閲覧できない
def test_8_student_cannot_see_others(client, db):
    login(client, TENNIS_REP)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=True, files=FULL_FILES, declared=("itinerary", "roster"))
    roster_att = db.scalar(select(Attachment).where(Attachment.report_id == rid, Attachment.is_restricted.is_(True)))

    # 別の学生: 詳細 403、一覧に出ない
    login(client, OTHER_STUDENT)
    assert client.get(f"/reports/{rid}").status_code == 403
    assert f"ACT-{rid:06d}" not in client.get("/reports").text
    assert client.get(f"/reports/{rid}/attachments/{roster_att.id}").status_code == 403
    assert client.get("/orgs").status_code == 403

    # 提出者本人でも参加者名簿 (限定保管先) はダウンロードできない
    login(client, TENNIS_REP)
    assert client.get(f"/reports/{rid}").status_code == 200
    assert client.get(f"/reports/{rid}/attachments/{roster_att.id}").status_code == 403

    # 顧問・保守担当も名簿は不可、職員・管理職は可
    for email in (ADVISOR, SYSADMIN):
        login(client, email)
        assert client.get(f"/reports/{rid}/attachments/{roster_att.id}").status_code == 403
    for email in (STAFF, MANAGER):
        login(client, email)
        assert client.get(f"/reports/{rid}/attachments/{roster_att.id}").status_code == 200

    # 管理職は状況を更新できない (閲覧のみ)
    login(client, MANAGER)
    assert client.post(f"/reports/{rid}/status", data={"status": "確認済", "remarks": ""}, follow_redirects=False).status_code == 403

    # 未ログインはログイン画面へ
    client.post("/auth/logout", follow_redirects=False)
    r = client.get("/reports", follow_redirects=False)
    assert r.status_code == 303 and "/auth/login" in r.headers["location"]


# シナリオ9: 年度部員名簿を提出 → 限定保管先に保存され、学生はダウンロードできない
def test_9_annual_roster_to_vault(client, db, app_env):
    login(client, TENNIS_REP)
    r = client.post("/rosters/new", data={"organization_id": str(org_id(db, "ORG-0001")), "fiscal_year": "2026", "note": "年度初め"},
                    files={"file": ("members.xlsx", b"members", "application/octet-stream")}, follow_redirects=False)
    assert r.status_code == 303
    from app.models import AnnualRoster

    roster = db.scalar(select(AnnualRoster).order_by(AnnualRoster.id.desc()))
    assert roster.stored_path.startswith("personal_info_vault/annual/2026/ORG-0001/")
    assert (app_env / roster.stored_path).exists()
    assert client.get(f"/rosters/{roster.id}/download").status_code == 403
    login(client, STAFF)
    assert client.get(f"/rosters/{roster.id}/download").status_code == 200


# シナリオ10: 自動処理が止まっても、登録内容から職員が手動で受付・通知できる
def test_10_manual_fallback(client, db):
    """受付後処理を通さずに登録された届 (フロー停止を想定) を、職員が画面から状況更新できる。"""
    from datetime import datetime

    from app.database import SessionLocal

    with SessionLocal() as s:
        rep = ActivityReport(organization_id=org_id(db, "ORG-0001"), content="手動登録テスト", start_at=datetime(2026, 11, 1, 9), end_at=datetime(2026, 11, 1, 17),
                             location="学外グラウンド", participants_count=5, leader_name="X", leader_phone="090", leader_email="x@example.ac.jp",
                             requires_precheck=True, applicant_name="田中 太郎", applicant_email=TENNIS_REP, application_no="ACT-MANUAL-1", source="手動登録")
        s.add(rep)
        s.commit()
        rid = rep.id
    login(client, STAFF)
    assert client.get(f"/reports/{rid}").status_code == 200
    client.post(f"/reports/{rid}/status", data={"status": "確認済", "remarks": "手動で受付"}, follow_redirects=False)
    assert len(notifications_for(db, rid, "result")) == 1


# 休止団体はフォームの選択肢に出ない (7.2 有効フラグ)
def test_inactive_org_hidden_from_form(client):
    login(client, TENNIS_REP)
    html = client.get("/reports/new").text
    assert "硬式テニス部" in html and "旧・写真部" not in html
