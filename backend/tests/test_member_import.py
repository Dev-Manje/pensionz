"""Bulk member upload and application form (FR-MEM-006, FR-MEM-007)."""
import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.models.member import ImportStatus, Member, MemberImport, MemberSalary
from app.services.io import member_import
from tests.factories import auth_headers
from tests.test_members import approve, body, checker, create, maker, setup  # noqa: F401 — fixtures


def _filled(client, user, scheme, rows: list[dict]) -> bytes:
    response = client.get("/api/v1/members/import-template", headers=auth_headers(user), params={"scheme_id": str(scheme.id)})
    assert response.status_code == 200
    wb = load_workbook(io.BytesIO(response.content))
    ws = wb["Members"]
    headers = [c.value.replace(" *", "") for c in ws[1]]
    for r, row in enumerate(rows, start=2):
        for key, value in row.items():
            label = next(c.label for c in member_import.COLUMNS if c.key == key)
            ws.cell(row=r, column=headers.index(label) + 1, value=value)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _upload(client, user, scheme, content, name="members.xlsx"):
    return client.post("/api/v1/members/imports", headers=auth_headers(user), data={"scheme_id": str(scheme.id)},
                       files={"file": (name, content, "application/octet-stream")})


GOOD = {"first_name": "Alinafe", "last_name": "Zulu", "gender": "F", "date_of_birth": date(1992, 4, 3), "id_type": "National ID",
        "id_number": "IMP-001", "category_code": "STF", "date_joined_fund": "2025-01-01", "basic_salary": "450,000",
        "bank_name": "National Bank of Malawi", "next_of_kin_relationship": "Spouse", "nationality": "Malawi"}


def test_template_lists_categories_and_guide(client, maker, setup):
    fund, scheme, category = setup
    content = client.get("/api/v1/members/import-template", headers=auth_headers(maker), params={"scheme_id": str(scheme.id)}).content
    wb = load_workbook(io.BytesIO(content))
    assert wb.sheetnames == ["Members", "Guide"]
    assert wb["Members"]["E1"].value == "First name *"
    guide = [c.value for c in wb["Guide"]["A"]]
    assert "Category code — allowed values" in guide and "STF" in guide


def test_upload_reports_row_errors_and_in_file_duplicates(client, db, maker, setup):
    fund, scheme, category = setup
    rows = [GOOD,
            {**GOOD, "id_number": "IMP-002"},  # same name + DOB as row 2
            {**GOOD, "first_name": "Bad", "gender": "X", "date_of_birth": "31/31/1990", "id_number": "IMP-003"},
            {**GOOD, "first_name": "NoCat", "category_code": "ZZZ", "id_number": "IMP-004"},
            {**GOOD, "first_name": "Child", "date_of_birth": date(2015, 1, 1), "id_number": "IMP-005"}]
    response = _upload(client, maker, scheme, _filled(client, maker, scheme, rows))
    assert response.status_code == 201, response.text
    batch = response.json()
    assert (batch["total_rows"], batch["valid_rows"]) == (5, 1)
    errors = {r["row"]: r["errors"] for r in batch["rows"]}
    assert errors[2] == []
    assert errors[3] == ["Same name and date of birth as row 2"]
    assert any("Gender" in e for e in errors[4]) and any("isn't a date" in e for e in errors[4])
    assert errors[5] == ["Category “ZZZ” isn't a category of this employer"]
    assert "accepts members from age 18" in errors[6][0]

    sheet = load_workbook(io.BytesIO(client.get(f"/api/v1/members/imports/{batch['id']}/errors", headers=auth_headers(maker)).content))["Members"]
    assert sheet.max_row == 5 and sheet.cell(row=2, column=len(member_import.COLUMNS) + 1).value.startswith("Row 3:")


def test_valid_rows_import_after_approval_with_salary(client, db, maker, checker, setup):
    fund, scheme, category = setup
    rows = [GOOD, {**GOOD, "first_name": "Tamanda", "id_number": "IMP-010", "basic_salary": None, "account_code": "LEG0042"},
            {**GOOD, "first_name": "Broken", "gender": None, "id_number": "IMP-011"}]
    batch = _upload(client, maker, scheme, _filled(client, maker, scheme, rows)).json()
    request = client.post(f"/api/v1/members/imports/{batch['id']}/submit", headers=auth_headers(maker))
    assert request.status_code == 202, request.text
    assert request.json()["payload"]["members_to_import"] == 2
    assert client.post(f"/api/v1/members/imports/{batch['id']}/submit", headers=auth_headers(maker)).status_code == 409
    assert approve(client, checker, request.json()["id"]).status_code == 200

    created = db.query(Member).filter_by(fund_id=fund.id).order_by(Member.first_name).all()
    assert [m.first_name for m in created] == ["Alinafe", "Tamanda"]
    assert created[1].account_code == "LEG0042"
    salary = db.query(MemberSalary).filter_by(member_id=created[0].id).one()
    assert salary.pensionable_salary == Decimal("450000.00") and salary.effective_from == date(2025, 1, 1)
    stored = db.query(MemberImport).filter_by(scheme_id=scheme.id).one()
    db.refresh(stored)
    assert (stored.status, stored.imported_rows) == (ImportStatus.imported, 2)


def test_row_that_became_invalid_is_skipped_on_approval(client, db, maker, checker, setup):
    fund, scheme, category = setup
    batch = _upload(client, maker, scheme, _filled(client, maker, scheme, [GOOD])).json()
    request = client.post(f"/api/v1/members/imports/{batch['id']}/submit", headers=auth_headers(maker)).json()
    # The same person is added one by one while the upload waits.
    create(client, db, maker, checker, fund, body(scheme, category, id_number="IMP-001", first_name="Alinafe", last_name="Zulu"))
    assert approve(client, checker, request["id"]).status_code == 200
    stored = db.query(MemberImport).filter_by(scheme_id=scheme.id).one()
    db.refresh(stored)
    assert stored.imported_rows == 0 and stored.rows[0]["errors"][0].startswith("Not imported:")


def test_upload_refuses_bad_files_and_wrong_roles(client, db, maker, setup):
    fund, scheme, category = setup
    assert _upload(client, maker, scheme, b"hello", name="members.txt").status_code == 400
    assert _upload(client, maker, scheme, b"first name,last name\nA,B\n", name="m.csv").status_code == 400  # missing columns
    from app.models.identity import UserRole
    from tests.factories import make_user
    viewer = make_user(db, UserRole.contributions_officer)
    assert _upload(client, viewer, scheme, b"x", name="m.xlsx").status_code == 403
    outsider = make_user(db, UserRole.member_admin)
    assert _upload(client, outsider, scheme, b"x", name="m.xlsx").status_code == 404


def test_application_form_pdf(client, maker, setup):
    fund, scheme, category = setup
    response = client.get("/api/v1/members/application-form", headers=auth_headers(maker), params={"scheme_id": str(scheme.id)})
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    assert client.get("/api/v1/members/application-form", headers=auth_headers(maker)).content.startswith(b"%PDF")
