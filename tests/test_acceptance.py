"""12. 受入要件・テスト の各シナリオを自動テストにしたもの。

実行:  pytest -v
"""
from __future__ import annotations

from sqlalchemy import select

from app.models import ActivityReport, Member, Notification, Organization

from .conftest import ITINERARY_FILE, ROSTER_TEXT, login, report_data, submit_full, submit_report

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


# シナリオ2: 対象活動を必要資料付きで提出 → 名簿は表として保存され、確認依頼が届く
def test_2_precheck_with_documents(client, db, app_env):
    login(client, TENNIS_REP)
    rid = submit_full(client, org_id=org_id(db, "ORG-0001"))
    r = get_report(db, rid)
    assert r.status.value == "未確認"
    assert r.missing_items == ""
    assert [a.kind.value for a in r.attachments] == ["行程等"]
    assert (app_env / r.attachments[0].stored_path).exists()
    assert [(p.student_no, p.name) for p in r.participants] == [("2023001", "田中 太郎"), ("2024001", "中村 健")]
    staff_req = notifications_for(db, rid, "staff_request")
    assert len(staff_req) == 1 and staff_req[0].to_email == STAFF and "名簿 2 名" in staff_req[0].body
    assert len(notifications_for(db, rid, "advisor_share")) == 1  # 顧問へ共有
    assert "確認中" in notifications_for(db, rid, "receipt")[0].subject


# シナリオ3: 対象活動を資料不足で提出 → 差戻し、不足内容の通知
def test_3_precheck_missing_documents(client, db):
    login(client, TENNIS_REP)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=True)  # 添付なし・名簿なし
    r = get_report(db, rid)
    assert r.status.value == "差戻し"
    assert "参加者名簿に参加者が登録されていません" in r.missing_items
    assert "行程表・活動計画書等が添付されていません" in r.missing_items
    missing = notifications_for(db, rid, "missing")
    assert len(missing) == 1 and "不足" in missing[0].subject and "参加者名簿" in missing[0].body
    assert notifications_for(db, rid, "staff_request") == []  # 職員への確認依頼は出さない


# シナリオ3b: 差戻された届を修正して再提出 → 同じ申請番号のまま「未確認」になり、履歴が残る
def test_3b_resubmit_after_return(client, db):
    login(client, TENNIS_REP)
    rid = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=True)
    assert get_report(db, rid).status.value == "差戻し"
    assert client.get(f"/reports/{rid}/edit").status_code == 200

    data = report_data(org_id=org_id(db, "ORG-0001"), precheck=True, roster=ROSTER_TEXT, declared=("itinerary",))
    r = client.post(f"/reports/{rid}/edit", data=data, files=ITINERARY_FILE, follow_redirects=False)
    assert r.status_code == 303
    rep = get_report(db, rid)
    assert rep.application_no == f"ACT-{rid:06d}"
    assert rep.status.value == "未確認" and rep.revision == 2 and rep.missing_items == ""
    assert len(rep.participants) == 2
    assert any(l.action == "再提出前の差戻し理由" for l in rep.logs)
    assert any("再提出" in n.subject for n in notifications_for(db, rid, "staff_request"))

    # 未確認になった届は再提出できない / 他人は編集できない
    assert client.get(f"/reports/{rid}/edit").status_code == 400
    login(client, OTHER_STUDENT)
    assert client.get(f"/reports/{rid}/edit").status_code == 403


# シナリオ3c: 名簿の貼り付けは 4 列以外を受け付けない (要配慮情報の持ち込み防止)
def test_3c_roster_rejects_extra_columns(client, db):
    login(client, TENNIS_REP)
    bad = "2023001\t田中 太郎\t工学部\t3\t既往歴あり\n"
    data = report_data(org_id=org_id(db, "ORG-0001"), precheck=True, roster=bad)
    r = client.post("/reports/new", data=data, follow_redirects=False)
    assert r.status_code == 400 and "4 列" in r.text


# シナリオ3d: 代表者は部員一覧から参加者を選べる。代表者でない学生は選べない
def test_3d_pick_participants_from_members(client, db):
    tennis = org_id(db, "ORG-0001")
    member_ids = [m.id for m in db.scalars(select(Member).where(Member.organization_id == tennis)).all()[:3]]
    login(client, TENNIS_REP)
    assert client.get(f"/rosters/{tennis}/members.json").json()["allowed"] is True
    data = report_data(org_id=tennis, precheck=True, roster="2099001\t追加 花子\t文学部\t1", declared=("itinerary",))
    data["member_ids"] = [str(i) for i in member_ids]
    r = client.post("/reports/new", data=data, files=ITINERARY_FILE, follow_redirects=False)
    assert r.status_code == 303
    rep = get_report(db, int(r.headers["location"].split("/")[2]))
    assert len(rep.participants) == 4   # 部員 3 名 + 貼り付け 1 名

    login(client, OTHER_STUDENT)
    assert client.get(f"/rosters/{tennis}/members.json").json()["allowed"] is False
    data["member_ids"] = [str(member_ids[0])]
    r = client.post("/reports/new", data=data, files=ITINERARY_FILE, follow_redirects=False)
    assert r.status_code == 400 and "代表者・副代表者だけ" in r.text


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

    login(client, STAFF)
    html = client.get("/dashboard").text
    assert f"ACT-{rid:06d}" in html and f"ACT-{rid2:06d}" in html


# シナリオ6: 職員が確認済へ変更 → 申請者へ結果通知が 1 回届く (再保存で重複しない)
def test_6_staff_confirms_once(client, db):
    login(client, TENNIS_REP)
    rid = submit_full(client, org_id=org_id(db, "ORG-0001"))
    login(client, STAFF)
    for _ in range(3):  # 同じ値で3回保存
        r = client.post(f"/reports/{rid}/status", data={"status": "確認済", "remarks": "帰着後に電話連絡すること"}, follow_redirects=False)
        assert r.status_code == 303
    results = notifications_for(db, rid, "result")
    assert len(results) == 1
    assert results[0].to_email == TENNIS_REP and "確認済" in results[0].subject and "帰着後" in results[0].body
    assert get_report(db, rid).status.value == "確認済"


# シナリオ7: 職員が差戻しへ変更 → 備考の理由を含む通知。学生が再提出すると再度確認依頼が出る
def test_7_staff_returns_with_reason(client, db):
    login(client, TENNIS_REP)
    rid = submit_full(client, org_id=org_id(db, "ORG-0001"))
    login(client, STAFF)
    client.post(f"/reports/{rid}/status", data={"status": "差戻し", "remarks": "行程表に宿泊先の住所を追記してください"}, follow_redirects=False)
    results = notifications_for(db, rid, "result")
    assert len(results) == 1 and "差戻し" in results[0].subject
    assert "宿泊先の住所" in results[0].body

    login(client, TENNIS_REP)
    data = report_data(org_id=org_id(db, "ORG-0001"), precheck=True, roster=ROSTER_TEXT, declared=("itinerary",),
                       itinerary_summary="10日: 移動 (宿泊先: ホテル△△ 〇〇市1-2-3)")
    r = client.post(f"/reports/{rid}/edit", data=data, follow_redirects=False)  # 既存の添付はそのまま残る
    assert r.status_code == 303
    rep = get_report(db, rid)
    assert rep.status.value == "未確認" and rep.revision == 2 and len(rep.attachments) == 1
    login(client, STAFF)
    client.post(f"/reports/{rid}/status", data={"status": "確認済", "remarks": ""}, follow_redirects=False)
    assert len(notifications_for(db, rid, "result")) == 2   # 再提出後の確認済は改めて通知される


# シナリオ8: 学生アカウントで一覧・他人の届・名簿にアクセス → 閲覧できない
def test_8_student_cannot_see_others(client, db):
    login(client, TENNIS_REP)
    rid = submit_full(client, org_id=org_id(db, "ORG-0001"))

    # 別の学生: 詳細 403、一覧に出ない、名簿 CSV 403
    login(client, OTHER_STUDENT)
    assert client.get(f"/reports/{rid}").status_code == 403
    assert f"ACT-{rid:06d}" not in client.get("/reports").text
    assert client.get(f"/reports/{rid}/participants.csv").status_code == 403
    assert client.get("/orgs").status_code == 403
    assert client.get("/dashboard").status_code == 403

    # 提出者本人は自分の届と名簿を見られるが CSV (名簿保管先の機能) は不可
    login(client, TENNIS_REP)
    html = client.get(f"/reports/{rid}").text
    assert "2023001" in html
    assert client.get(f"/reports/{rid}/participants.csv").status_code == 403

    # 顧問は届は見られるが参加者名簿は見られない。保守担当も名簿は不可
    login(client, ADVISOR)
    html = client.get(f"/reports/{rid}").text
    assert "2023001" not in html and "指定職員・管理職のみ" in html
    assert client.get(f"/reports/{rid}/participants.csv").status_code == 403
    login(client, SYSADMIN)
    assert "2023001" not in client.get(f"/reports/{rid}").text
    assert client.get(f"/reports/{rid}/participants.csv").status_code == 403

    # 職員・管理職は名簿を見られる。管理職は状況を更新できない
    for email in (STAFF, MANAGER):
        login(client, email)
        assert "2023001" in client.get(f"/reports/{rid}").text
        assert client.get(f"/reports/{rid}/participants.csv").status_code == 200
    login(client, MANAGER)
    assert client.post(f"/reports/{rid}/status", data={"status": "確認済", "remarks": ""}, follow_redirects=False).status_code == 403

    # 未ログインはログイン画面へ
    client.post("/auth/logout", follow_redirects=False)
    r = client.get("/reports", follow_redirects=False)
    assert r.status_code == 303 and "/auth/login" in r.headers["location"]


# シナリオ9: 年度部員名簿を登録 → 代表者だけ更新でき、職員は全団体を閲覧できる
def test_9_annual_roster(client, db):
    alpine = org_id(db, "ORG-0002")
    login(client, ALPINE_VICE)   # 副代表は登録できる
    text = "2023101\t山田 一郎\t理学部\t3\n2024101\t鈴木 花子\t工学部\t2\n"
    r = client.post(f"/rosters/{alpine}", data={"fiscal_year": "2026", "roster_text": text}, follow_redirects=False)
    assert r.status_code == 303
    members = db.scalars(select(Member).where(Member.organization_id == alpine, Member.fiscal_year == 2026)).all()
    assert sorted(m.student_no for m in members) == ["2023101", "2024101"]

    # 更新 (退部 1 名) → 置き換わる
    r = client.post(f"/rosters/{alpine}", data={"fiscal_year": "2026", "roster_text": "2023101\t山田 一郎\t理学部\t3\n"}, follow_redirects=False)
    db.expire_all()
    members = db.scalars(select(Member).where(Member.organization_id == alpine, Member.fiscal_year == 2026)).all()
    assert [m.student_no for m in members] == ["2023101"]

    # 5 列の行は拒否
    r = client.post(f"/rosters/{alpine}", data={"fiscal_year": "2026", "roster_text": "2023101\t山田\t理学部\t3\t喘息\n"}, follow_redirects=False)
    assert r.status_code == 400

    # 代表でない学生は登録も閲覧も不可。顧問・保守も不可。職員・管理職は閲覧可
    login(client, OTHER_STUDENT)
    assert client.post(f"/rosters/{alpine}", data={"fiscal_year": "2026", "roster_text": text}, follow_redirects=False).status_code == 403
    assert client.get(f"/rosters/{alpine}?fiscal_year=2026").status_code == 403
    for email in (ADVISOR, SYSADMIN):
        login(client, email)
        assert client.get("/rosters").status_code == 403
    for email in (STAFF, MANAGER):
        login(client, email)
        assert "山田 一郎" in client.get(f"/rosters/{alpine}?fiscal_year=2026").text
        assert client.get(f"/rosters/{alpine}/members.csv?fiscal_year=2026").status_code == 200


# シナリオ10: 自動処理が止まっても、登録内容から職員が手動で受付・通知できる
def test_10_manual_fallback(client, db):
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


# ダッシュボード: いま活動中 / 7日以内 / 検索
def test_dashboard(client, db):
    from datetime import datetime, timedelta

    now = datetime.now()
    fmt = "%Y-%m-%dT%H:%M"
    login(client, TENNIS_REP)
    ongoing = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=False, content="いま活動中のテスト",
                            location="△△湖 キャンプ場", start_at=(now - timedelta(hours=2)).strftime(fmt), end_at=(now + timedelta(hours=5)).strftime(fmt))
    upcoming = submit_report(client, org_id=org_id(db, "ORG-0001"), precheck=False, content="3日後のテスト",
                             start_at=(now + timedelta(days=3)).strftime(fmt), end_at=(now + timedelta(days=3, hours=8)).strftime(fmt))
    login(client, STAFF)
    html = client.get("/dashboard").text
    assert f"ACT-{ongoing:06d}" in html and f"ACT-{upcoming:06d}" in html
    html = client.get("/dashboard", params={"q": "△△湖"}).text
    assert f"ACT-{ongoing:06d}" in html and "3日後のテスト" not in html.split("いま学外で活動中")[0]
    html = client.get("/dashboard", params={"on": (now + timedelta(days=3)).strftime("%Y-%m-%d")}).text
    assert f"ACT-{upcoming:06d}" in html
    # 職員のトップはダッシュボードへ
    r = client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/dashboard"


# 休止団体はフォームの選択肢に出ない (7.2 有効フラグ)
def test_inactive_org_hidden_from_form(client):
    login(client, TENNIS_REP)
    html = client.get("/reports/new").text
    assert "硬式テニス部" in html and "旧・写真部" not in html
