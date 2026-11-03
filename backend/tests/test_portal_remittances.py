"""Remitting contributions from the principal officer portal: schedules built and
checked row by row, sent with a one-time code to the allocation queue; payment
notices with proof of payment; month-by-month history. Employer EMP01 has two
members on 5% / 10% of 200,000 and 100,000."""
import re
from datetime import date
from decimal import Decimal

import pytest

from app.core import storage
from app.models.contribution import ContributionSchedule, ScheduleSource, ScheduleStatus
from app.models.fund import Fund
from app.models.identity import UserRole
from app.models.notification import NotificationOutbox, UserNotification
from app.models.scheme import SchemeOfficer
from app.services import fund_access, schedules
from tests.factories import auth_headers, make_user
from tests.test_arrears import staff, world  # noqa: F401 — fixtures

PO = "/api/v1/po"
OCT = "2026-10-01"
PDF = b"%PDF-1.4 proof"


@pytest.fixture(autouse=True)
def memory_storage(monkeypatch):
    files: dict[str, bytes] = {}

    def upload(content, content_type, prefix):
        files[f"{prefix}/{len(files)}"] = content
        return f"{prefix}/{len(files) - 1}"

    monkeypatch.setattr(storage, "upload_file", upload)
    monkeypatch.setattr(storage, "download_file", lambda key: files[key])
    return files


@pytest.fixture
def scheme(world):
    return world[1]


@pytest.fixture
def officer(db, scheme):
    user = make_user(db, UserRole.principal_officer)
    db.add(SchemeOfficer(scheme_id=scheme.id, user_id=user.id))
    db.flush()
    return user


@pytest.fixture
def contributions(db, scheme):
    user = make_user(db, UserRole.contributions_officer)
    fund_access.grant(db, user.id, scheme.fund_id, None)
    db.flush()
    return user


def code_for(client, db, user) -> str:
    assert client.post(f"{PO}/remit-code", headers=auth_headers(user)).status_code == 202
    row = (db.query(NotificationOutbox).filter_by(recipient_user_id=user.id, event="auth.one_time_code")
           .order_by(NotificationOutbox.created_at.desc()).first())
    assert "send contributions" in row.body
    return re.search(r"\b(\d{6})\b", row.body).group(1)


def start(client, user, scheme, month=OCT, supplementary=False):
    return client.post(f"{PO}/schemes/{scheme.id}/schedules", headers=auth_headers(user),
                       json={"contribution_month": month, "supplementary": supplementary})


def test_schedule_is_prefilled_checked_and_sent_with_a_code(client, db, scheme, officer, contributions):
    response = start(client, officer, scheme)
    assert response.status_code == 201, response.text
    s = response.json()
    assert s["can_edit"] and s["source"] == "portal" and s["line_count"] == 2 and s["error_count"] == 0
    assert Decimal(s["total"]) == Decimal("45000.00")  # (10,000 + 20,000) + (5,000 + 10,000)
    assert start(client, officer, scheme).status_code == 409  # one main schedule per month

    sid = s["id"]
    assert client.post(f"{PO}/schedules/{sid}/submit", headers=auth_headers(officer), json={}).status_code == 422
    code = code_for(client, db, officer)
    wrong = f"{(int(code) + 1) % 10 ** 6:06d}"
    bad = client.post(f"{PO}/schedules/{sid}/submit", headers=auth_headers(officer), json={"code": wrong})
    assert bad.status_code == 400 and "tries left" in bad.json()["detail"]
    sent = client.post(f"{PO}/schedules/{sid}/submit", headers=auth_headers(officer), json={"code": code})
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "ready" and sent.json()["can_edit"] is False
    # In the contributions officers' allocation queue, and they're told.
    assert db.query(UserNotification).filter_by(user_id=contributions.id, event="schedule.portal_submitted").count() == 1
    # Sent: no more changes, and the code is used up.
    assert client.post(f"{PO}/schedules/{sid}/fill-expected", headers=auth_headers(officer)).status_code == 409
    assert client.post(f"{PO}/schedules/{sid}/cancel", headers=auth_headers(officer)).status_code == 409


def test_row_errors_block_sending_without_using_the_code(client, db, scheme, officer):
    s = start(client, officer, scheme).json()
    bad = client.post(f"{PO}/schedules/{s['id']}/lines", headers=auth_headers(officer),
                      json={"account_code": "NOPE001", "employee": "100", "employer": "200"}).json()
    assert bad["error_count"] == 1
    line = next(l for l in bad["lines"] if l["account_code"] == "NOPE001")
    assert line["errors"] == ["No member of this fund has that account code"]
    code = code_for(client, db, officer)
    refused = client.post(f"{PO}/schedules/{s['id']}/submit", headers=auth_headers(officer), json={"code": code})
    assert refused.status_code == 400 and "1 row(s) with errors" in refused.json()["detail"]
    fixed = client.delete(f"{PO}/schedules/{s['id']}/lines/{line['id']}", headers=auth_headers(officer)).json()
    assert fixed["error_count"] == 0
    # The same code still works.
    assert client.post(f"{PO}/schedules/{s['id']}/submit", headers=auth_headers(officer), json={"code": code}).status_code == 200


def test_upload_the_template_back(client, db, scheme, officer):
    s = start(client, officer, scheme).json()
    template = client.get(f"{PO}/schemes/{scheme.id}/schedules/template", params={"month": OCT}, headers=auth_headers(officer))
    assert template.status_code == 200 and template.content[:2] == b"PK"
    up = client.post(f"{PO}/schedules/{s['id']}/upload", headers=auth_headers(officer),
                     files={"file": ("october.xlsx", template.content, "application/octet-stream")})
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["source"] == "portal" and body["can_edit"] and body["filename"] == "october.xlsx" and body["line_count"] == 2
    unreadable = client.post(f"{PO}/schedules/{s['id']}/upload", headers=auth_headers(officer),
                             files={"file": ("notes.txt", b"hello", "text/plain")})
    assert unreadable.status_code == 400


def test_schedule_prepared_by_staff_is_read_only(client, db, scheme, officer, staff):
    fund = db.get(Fund, scheme.fund_id)
    staff_draft = schedules.create(db, staff, fund, scheme.id, date(2026, 9, 1), supplementary=False, source=ScheduleSource.manual, prefill=True)
    got = client.get(f"{PO}/schedules/{staff_draft.id}", headers=auth_headers(officer))
    assert got.status_code == 200 and got.json()["can_edit"] is False
    line_id = got.json()["lines"][0]["id"]
    assert client.put(f"{PO}/schedules/{staff_draft.id}/lines/{line_id}", headers=auth_headers(officer),
                      json={"account_code": "EMP010001", "employee": "1"}).status_code == 409


def test_payment_notice_proof_and_history(client, db, scheme, officer):
    code = code_for(client, db, officer)
    body = {"amount": "45000.00", "payment_date": "2026-11-01", "payment_method": "eft", "payer_reference": "TT2611-01",
            "contribution_month": OCT, "code": code}
    response = client.post(f"{PO}/schemes/{scheme.id}/payment-notices", headers=auth_headers(officer), json=body)
    assert response.status_code == 201, response.text
    notice = response.json()
    assert notice["status"] == "notified" and notice["notice_number"] and notice["can_add_proof"] and notice["document_kind"] == "acknowledgement"
    # The same code can't send a second notice.
    assert client.post(f"{PO}/schemes/{scheme.id}/payment-notices", headers=auth_headers(officer), json=body).status_code == 400

    proof = client.post(f"{PO}/remittances/{notice['id']}/proof", headers=auth_headers(officer),
                        files={"file": ("slip.pdf", PDF, "application/pdf")})
    assert proof.status_code == 200 and proof.json()["has_proof"]
    assert client.get(f"{PO}/remittances/{notice['id']}/proof", headers=auth_headers(officer)).content == PDF
    pdf = client.get(f"{PO}/remittances/{notice['id']}/document", headers=auth_headers(officer))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    months = client.get(f"{PO}/schemes/{scheme.id}/remittances", headers=auth_headers(officer)).json()
    october = next(m for m in months if m["month"] == OCT)
    assert october["stage"] == "payment_only" and Decimal(october["noted"]) == Decimal("45000.00")
    assert [p["notice_number"] for p in october["payments"]] == [notice["notice_number"]]


def test_notice_checks_come_before_the_code(client, db, scheme, officer):
    code = code_for(client, db, officer)
    future = client.post(f"{PO}/schemes/{scheme.id}/payment-notices", headers=auth_headers(officer),
                         json={"amount": "100", "payment_date": "2099-01-01", "payment_method": "eft", "code": code})
    assert future.status_code == 400 and "future" in future.json()["detail"]
    ok = client.post(f"{PO}/schemes/{scheme.id}/payment-notices", headers=auth_headers(officer),
                     json={"amount": "100", "payment_date": "2026-11-01", "payment_method": "eft", "code": code})
    assert ok.status_code == 201
    months = client.get(f"{PO}/schemes/{scheme.id}/remittances", headers=auth_headers(officer)).json()
    assert months[-1]["month"] is None and len(months[-1]["payments"]) == 1


def test_other_employers_and_staff_are_kept_out(client, db, scheme, officer, staff):
    s = start(client, officer, scheme).json()
    stranger = make_user(db, UserRole.principal_officer)
    for path in (f"/schedules/{s['id']}", f"/schemes/{scheme.id}/remittances"):
        assert client.get(PO + path, headers=auth_headers(stranger)).status_code == 404
        assert client.get(PO + path, headers=auth_headers(staff)).status_code == 403
    assert start(client, stranger, scheme).status_code == 404
    assert client.post(f"{PO}/schedules/{s['id']}/cancel", headers=auth_headers(stranger)).status_code == 404
    cancelled = client.post(f"{PO}/schedules/{s['id']}/cancel", headers=auth_headers(officer))
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert db.get(ContributionSchedule, s["id"]).status == ScheduleStatus.cancelled
