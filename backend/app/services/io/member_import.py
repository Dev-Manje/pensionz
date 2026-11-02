"""Bulk member upload (FR-MEM-006).

1. `template(db, scheme)` — an Excel workbook: a "Members" sheet with one column per
   field (required ones marked *), drop-downs where the values are fixed, and a
   "Guide" sheet listing what each column takes and the allowed codes.
2. `upload(...)` — reads the file (.xlsx or .csv), checks every row with the same
   rules as a single new member, plus duplicates within the file; stores a
   `member_import` batch with each row's values, errors and warnings.
3. `errors_workbook(batch)` — the rows with errors and why, to fix and re-upload.
4. `submit(...)` — the valid rows go to a member checker (approval kind
   `member_import`); approval creates them (and their first salary, if given).
   Rows that have become invalid since are skipped and reported on the batch."""
import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.category import BenefitCategory, CategoryStatus
from app.models.fund import Fund
from app.models.identity import User
from app.models.member import ImportStatus, MemberImport, MemberSalary
from app.models.reference import Bank, BankBranch, Country, ReferenceItem, ReferenceList
from app.models.scheme import Scheme
from app.schemas.member import MemberCreateIn
from app.services import approvals, audit, members

KIND = "member_import"
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000
GENDERS = {"f": "female", "female": "female", "m": "male", "male": "male"}
CIVIL = {"single": "single", "married": "married", "divorced": "divorced", "widowed": "widowed", "widow": "widowed", "widower": "widowed"}


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    required: bool = False
    help: str = ""
    width: int = 18


COLUMNS: tuple[Column, ...] = (
    Column("account_code", "Account code", help="Leave empty to generate one. Give it only for members moving from another system."),
    Column("employee_no", "Employee number"),
    Column("old_member_no", "Old member number"),
    Column("salutation", "Title", help="Mr, Mrs, Ms, Miss, Dr …"),
    Column("first_name", "First name", True),
    Column("other_names", "Other names"),
    Column("last_name", "Last name", True),
    Column("maiden_name", "Maiden name"),
    Column("gender", "Gender", True, "Female or Male", 10),
    Column("date_of_birth", "Date of birth", True, "A date cell, or YYYY-MM-DD / DD/MM/YYYY", 14),
    Column("nationality", "Nationality", help="Country code (MW) or name", width=12),
    Column("id_type", "ID type", help="See the Guide sheet", width=14),
    Column("id_number", "ID number"),
    Column("civil_status", "Civil status", help="Single, Married, Divorced or Widowed", width=12),
    Column("mobile", "Mobile"),
    Column("telephone", "Telephone"),
    Column("email", "Email", width=24),
    Column("physical_address", "Physical address", width=28),
    Column("postal_address", "Postal address", width=28),
    Column("category_code", "Category code", True, "A benefit category code of this employer (see the Guide sheet)", 14),
    Column("date_joined_fund", "Joined the fund", True, "Date", 14),
    Column("date_joined_employer", "Joined the employer", help="Date", width=14),
    Column("basic_salary", "Monthly basic salary", help="MWK; recorded as the first salary from the join date", width=16),
    Column("bank_name", "Bank", help="Bank name as on the Guide sheet", width=22),
    Column("bank_branch", "Bank branch"),
    Column("bank_account_name", "Bank account name", width=22),
    Column("bank_account_number", "Bank account number"),
    Column("next_of_kin_name", "Next of kin name", width=22),
    Column("next_of_kin_relationship", "Next of kin relationship", help="See the Guide sheet"),
    Column("next_of_kin_phone", "Next of kin phone"),
    Column("upid", "UPID"),
)
BY_LABEL = {c.label.lower(): c for c in COLUMNS}


def _bad(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


def _scheme_in_fund(db: Session, scheme_id: uuid.UUID, fund: Fund) -> Scheme:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or scheme.fund_id != fund.id:
        raise _bad("Choose an employer of this fund")
    return scheme


# ---- template


def _lists(db: Session, scheme: Scheme) -> dict[str, list[tuple[str, str]]]:
    def ref(key):
        return [(r.code, r.name) for r in db.execute(select(ReferenceItem).where(ReferenceItem.list_key == key, ReferenceItem.active.is_(True))
                                                       .order_by(ReferenceItem.sort_order)).scalars()]
    categories = db.execute(select(BenefitCategory).where(BenefitCategory.scheme_id == scheme.id, BenefitCategory.status == CategoryStatus.active)
                            .order_by(BenefitCategory.code)).scalars()
    banks = db.execute(select(Bank).where(Bank.active.is_(True)).order_by(Bank.name)).scalars()
    return {
        "Category code": [(c.code, c.name) for c in categories],
        "Gender": [("Female", ""), ("Male", "")],
        "Title": ref(ReferenceList.salutation),
        "ID type": ref(ReferenceList.id_type),
        "Civil status": [("Single", ""), ("Married", ""), ("Divorced", ""), ("Widowed", "")],
        "Next of kin relationship": ref(ReferenceList.relationship),
        "Bank": [(b.name, ", ".join(br.name for br in b.branches if br.active)) for b in banks],
    }


def template(db: Session, fund: Fund, scheme: Scheme) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Members"
    head_fill, req_fill = PatternFill("solid", fgColor="DCE9EC"), PatternFill("solid", fgColor="F6D7B0")
    for i, col in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=i, value=col.label + (" *" if col.required else ""))
        cell.font, cell.fill = Font(bold=True), req_fill if col.required else head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(i)].width = col.width
    ws.freeze_panes = "A2"
    lists = _lists(db, scheme)

    guide = wb.create_sheet("Guide")
    guide["A1"] = f"Member upload for {scheme.code} — {scheme.name} ({fund.code})"
    guide["A1"].font = Font(bold=True, size=13)
    guide["A2"] = "Fill one row per member on the Members sheet. Columns marked * are required. Don't rename or reorder the headings."
    guide.append([])
    guide.append(["Column", "Required", "What to enter"])
    for c in guide[4]:
        c.font = Font(bold=True)
    for col in COLUMNS:
        guide.append([col.label, "Yes" if col.required else "", col.help])
    row = guide.max_row + 2
    for name, values in lists.items():
        guide.cell(row=row, column=1, value=f"{name} — allowed values").font = Font(bold=True)
        row += 1
        for code, label in values:
            guide.cell(row=row, column=1, value=code)
            guide.cell(row=row, column=2, value=label)
            row += 1
        row += 1
    guide.column_dimensions["A"].width, guide.column_dimensions["B"].width, guide.column_dimensions["C"].width = 30, 40, 70

    # Drop-downs on the Members sheet for the short fixed lists.
    for name, values in lists.items():
        if name == "Bank" or not values:
            continue
        options = ",".join(code for code, _ in values)
        if len(options) > 250:
            continue
        idx = next(i for i, c in enumerate(COLUMNS, start=1) if c.label == name)
        letter = get_column_letter(idx)
        dv = DataValidation(type="list", formula1=f'"{options}"', allow_blank=True, showErrorMessage=True,
                            errorTitle=name, error=f"Choose a value from the list (see the Guide sheet).")
        ws.add_data_validation(dv)
        dv.add(f"{letter}2:{letter}{MAX_ROWS + 1}")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---- reading


def _read_rows(filename: str, content: bytes) -> list[tuple[int, dict]]:
    if len(content) > MAX_BYTES:
        raise _bad("The file is larger than 5 MB — split it into smaller files")
    name = (filename or "").lower()
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        table = list(csv.reader(io.StringIO(text)))
    elif name.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            raise _bad("That file couldn't be read as an Excel workbook (.xlsx)")
        ws = wb["Members"] if "Members" in wb.sheetnames else wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        raise _bad("Upload the template as .xlsx (or .csv)")
    if not table:
        raise _bad("The file is empty")
    header = [str(h or "").replace("*", "").strip().lower() for h in table[0]]
    keys = [BY_LABEL[h].key if h in BY_LABEL else None for h in header]
    missing = [c.label for c in COLUMNS if c.required and c.key not in keys]
    if missing:
        raise _bad(f"These columns are missing: {', '.join(missing)}. Use the template and keep its headings.")
    rows = []
    for n, raw in enumerate(table[1:], start=2):
        values = {k: v for k, v in zip(keys, raw) if k}
        if all(v is None or str(v).strip() == "" for v in values.values()):
            continue
        rows.append((n, values))
    if not rows:
        raise _bad("There are no members in the file")
    if len(rows) > MAX_ROWS:
        raise _bad(f"Up to {MAX_ROWS} members per file — this one has {len(rows)}")
    return rows


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def _date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"“{s}” isn't a date (use YYYY-MM-DD or DD/MM/YYYY)")


class _Lookups:
    def __init__(self, db: Session, scheme: Scheme):
        def ref(key):
            items = db.execute(select(ReferenceItem).where(ReferenceItem.list_key == key)).scalars().all()
            return {**{i.code.lower(): i.code for i in items}, **{i.name.lower(): i.code for i in items}}
        self.salutation, self.id_type, self.relationship = ref(ReferenceList.salutation), ref(ReferenceList.id_type), ref(ReferenceList.relationship)
        countries = db.execute(select(Country)).scalars().all()
        self.country = {**{c.code.lower(): c.code for c in countries}, **{c.code3.lower(): c.code for c in countries},
                        **{c.name.lower(): c.code for c in countries}}
        self.categories = {c.code.upper(): c for c in db.execute(select(BenefitCategory).where(BenefitCategory.scheme_id == scheme.id)).scalars()}
        self.banks = db.execute(select(Bank)).scalars().all()


def _pick(lookup: dict, value, what: str):
    text = _text(value)
    if text is None:
        return None
    found = lookup.get(text.lower())
    if found is None:
        raise ValueError(f"{what} “{text}” isn't on the list")
    return found


def _convert(raw: dict, look: _Lookups) -> tuple[dict, dict, list[str]]:
    """Template values → MemberCreateIn values (plus extras), with every conversion problem."""
    errors, extras = [], {}
    v: dict = {}
    for key in ("account_code", "employee_no", "old_member_no", "first_name", "other_names", "last_name", "maiden_name", "id_number",
                "mobile", "telephone", "email", "physical_address", "postal_address", "bank_account_name", "bank_account_number",
                "next_of_kin_name", "next_of_kin_phone", "upid"):
        v[key] = _text(raw.get(key))

    def attempt(key, fn):
        try:
            return fn()
        except ValueError as e:
            errors.append(str(e))
            return None

    gender = _text(raw.get("gender"))
    v["gender"] = GENDERS.get((gender or "").lower()) if gender else None
    if gender and v["gender"] is None:
        errors.append(f"Gender “{gender}” — use Female or Male")
    civil = _text(raw.get("civil_status"))
    v["civil_status_current"] = CIVIL.get((civil or "").lower()) if civil else None
    if civil and v["civil_status_current"] is None:
        errors.append(f"Civil status “{civil}” — use Single, Married, Divorced or Widowed")
    for key in ("date_of_birth", "date_joined_fund", "date_joined_employer"):
        v[key] = attempt(key, lambda k=key: _date(raw.get(k)))
    v["salutation"] = attempt("salutation", lambda: _pick(look.salutation, raw.get("salutation"), "Title"))
    v["id_type"] = attempt("id_type", lambda: _pick(look.id_type, raw.get("id_type"), "ID type"))
    v["nationality"] = attempt("nationality", lambda: _pick(look.country, raw.get("nationality"), "Nationality"))
    v["next_of_kin_relationship"] = attempt("rel", lambda: _pick(look.relationship, raw.get("next_of_kin_relationship"), "Next of kin relationship"))

    code = (_text(raw.get("category_code")) or "").upper()
    category = look.categories.get(code)
    if code and category is None:
        errors.append(f"Category “{code}” isn't a category of this employer")
    v["category_id"] = category.id if category else None

    bank_name, branch_name = _text(raw.get("bank_name")), _text(raw.get("bank_branch"))
    v["bank_id"] = v["bank_branch_id"] = None
    if bank_name:
        bank = next((b for b in look.banks if bank_name.lower() in {b.name.lower(), (b.short_name or "").lower()}), None)
        if bank is None:
            errors.append(f"Bank “{bank_name}” isn't on the list")
        else:
            v["bank_id"] = bank.id
            if branch_name:
                branch = next((br for br in bank.branches if br.name.lower() == branch_name.lower()), None)
                if branch is None:
                    errors.append(f"Branch “{branch_name}” isn't a branch of {bank.name}")
                else:
                    v["bank_branch_id"] = branch.id
    salary = _text(raw.get("basic_salary"))
    if salary:
        try:
            amount = Decimal(salary.replace(",", ""))
            if amount <= 0:
                raise InvalidOperation
            extras["basic_salary"] = str(amount.quantize(Decimal("0.01")))
        except InvalidOperation:
            errors.append(f"Monthly basic salary “{salary}” isn't an amount")
    v["preferred_contact"] = None
    return v, extras, errors


def _pydantic_errors(e: ValidationError) -> list[str]:
    labels = {c.key: c.label for c in COLUMNS}
    labels.update(civil_status_current="Civil status", category_id="Category code")
    out = []
    for err in e.errors():
        field = str(err["loc"][0]) if err.get("loc") else ""
        msg = err["msg"].replace("Value error, ", "")
        if err["type"] == "missing" or (err["type"] == "string_too_short" and "at least 1" in msg):
            out.append(f"{labels.get(field, field)} is required")
        else:
            out.append(f"{labels.get(field, field)}: {msg}")
    return out


def check_rows(db: Session, fund: Fund, scheme: Scheme, rows: list[tuple[int, dict]]) -> list[dict]:
    look = _Lookups(db, scheme)
    out, seen_ids, seen_people = [], {}, {}
    for n, raw in rows:
        values, extras, errors = _convert(raw, look)
        warnings: list[str] = []
        data = None
        if not errors:
            try:
                data = MemberCreateIn(**{**values, "scheme_id": scheme.id})
            except ValidationError as e:
                errors += _pydantic_errors(e)
        if data is not None:
            d = {k: v for k, v in data.model_dump().items() if k in members.DETAIL_FIELDS}
            try:
                members._check_details(db, fund, d, None)
                members._check_employment(db, fund, data.scheme_id, data.category_id, data.date_joined_fund, data.date_of_birth, new=True)
                if data.account_code:
                    members._check_account_code(db, fund, data.account_code)
                members._check_against_pending(db, fund, d, data.account_code)
            except HTTPException as e:
                errors.append(str(e.detail))
            key = members.id_key(data.id_number)
            person = (data.first_name.lower(), data.last_name.lower(), data.date_of_birth)
            if key and key in seen_ids:
                errors.append(f"Same ID number as row {seen_ids[key]}")
            elif person in seen_people:
                errors.append(f"Same name and date of birth as row {seen_people[person]}")
            if key:
                seen_ids.setdefault(key, n)
            seen_people.setdefault(person, n)
            if not errors:
                dups = members.find_duplicates(db, id_number=data.id_number, first_name=data.first_name, last_name=data.last_name,
                                               date_of_birth=data.date_of_birth)
                warnings += members._duplicate_lines(dups)
        out.append({"row": n, "raw": audit._jsonable({k: _text(v) if not isinstance(v, (date, datetime)) else v for k, v in raw.items()}),
                    "values": audit._jsonable({**data.model_dump(), **extras}) if data is not None and not errors else None,
                    "errors": errors, "warnings": warnings, "member_id": None})
    return out


# ---- batches


def upload(db: Session, user: User, fund: Fund, scheme_id: uuid.UUID, filename: str, content: bytes) -> MemberImport:
    if fund.fund_type in members.NO_EMPLOYER_FUNDS:
        raise _bad("Bulk upload is for employer funds; add personal pension holders one at a time from their KYC")
    scheme = _scheme_in_fund(db, scheme_id, fund)
    rows = check_rows(db, fund, scheme, _read_rows(filename, content))
    # A fresh upload for the same employer replaces an earlier one that was never submitted.
    for old in db.execute(select(MemberImport).where(MemberImport.scheme_id == scheme.id, MemberImport.status == ImportStatus.validated,
                                                     MemberImport.uploaded_by_user_id == user.id)).scalars():
        old.status = ImportStatus.cancelled
    batch = MemberImport(fund_id=fund.id, scheme_id=scheme.id, filename=(filename or "upload")[:200], status=ImportStatus.validated, rows=rows,
                         total_rows=len(rows), valid_rows=sum(1 for r in rows if not r["errors"]), uploaded_by_user_id=user.id)
    db.add(batch)
    db.flush()
    audit.record(db, user.id, "member_import", batch.id, "uploaded", after={"file": batch.filename, "rows": batch.total_rows,
                                                                           "valid": batch.valid_rows}, fund_id=fund.id)
    db.commit()
    db.refresh(batch)
    return batch


def errors_workbook(batch: MemberImport) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Members"
    for i, col in enumerate(COLUMNS, start=1):
        ws.cell(row=1, column=i, value=col.label + (" *" if col.required else "")).font = Font(bold=True)
        ws.column_dimensions[get_column_letter(i)].width = col.width
    err_col = len(COLUMNS) + 1
    ws.cell(row=1, column=err_col, value="Errors (delete this column before re-uploading)").font = Font(bold=True, color="B00020")
    ws.column_dimensions[get_column_letter(err_col)].width = 70
    r = 2
    for row in batch.rows:
        if not row["errors"]:
            continue
        for i, col in enumerate(COLUMNS, start=1):
            ws.cell(row=r, column=i, value=row["raw"].get(col.key))
        ws.cell(row=r, column=err_col, value=f"Row {row['row']}: " + "; ".join(row["errors"])).alignment = Alignment(wrap_text=True)
        r += 1
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _member_line(values: dict) -> str:
    return f"{values['first_name']} {values['last_name']} (born {values['date_of_birth']})"


def submit(db: Session, user: User, batch: MemberImport) -> ApprovalRequest:
    if batch.status != ImportStatus.validated:
        raise HTTPException(status.HTTP_409_CONFLICT, "This upload has already been submitted or withdrawn")
    if batch.uploaded_by_user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who uploaded the file can submit it")
    valid = [r for r in batch.rows if not r["errors"]]
    if not valid:
        raise _bad("No rows can be imported — fix the errors and upload the file again")
    scheme = db.get(Scheme, batch.scheme_id)
    fund = db.get(Fund, batch.fund_id)
    lines = [_member_line(r["values"]) for r in valid[:25]] + ([f"… and {len(valid) - 25} more"] if len(valid) > 25 else [])
    request = approvals.submit(
        db, user, KIND, entity_type="member_import", entity_id=batch.id,
        summary=f"Import {len(valid)} new member{'s' if len(valid) != 1 else ''} for {scheme.code} ({fund.code}) from {batch.filename}",
        payload={"action": "import", "employer": f"{scheme.code} — {scheme.name}", "file": batch.filename,
                 "members_to_import": len(valid), "rows_left_out_with_errors": batch.total_rows - len(valid),
                 "possible_duplicates": sum(1 for r in valid if r["warnings"]) or None, "members": lines, "_import_id": str(batch.id)},
        fund_id=batch.fund_id,
    )
    batch.status, batch.approval_request_id = ImportStatus.pending_approval, request.id
    db.commit()
    db.refresh(request)
    return request


def cancel(db: Session, user: User, batch: MemberImport) -> MemberImport:
    if batch.status != ImportStatus.validated:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an upload that hasn't been submitted can be withdrawn here")
    batch.status = ImportStatus.cancelled
    db.commit()
    db.refresh(batch)
    return batch


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    batch = db.execute(select(MemberImport).where(MemberImport.id == uuid.UUID(request.payload["_import_id"])).with_for_update()).scalar_one()
    fund = db.get(Fund, batch.fund_id)
    rows, imported = [dict(r) for r in batch.rows], 0
    for row in rows:
        if row["errors"]:
            continue
        data = MemberCreateIn(**{k: v for k, v in row["values"].items() if k in MemberCreateIn.model_fields})
        d = {k: v for k, v in data.model_dump().items() if k in members.DETAIL_FIELDS}
        try:
            members._check_details(db, fund, d, None)
            members._check_employment(db, fund, data.scheme_id, data.category_id, data.date_joined_fund, data.date_of_birth, new=True)
            if data.account_code:
                members._check_account_code(db, fund, data.account_code)
        except HTTPException as e:
            row["errors"] = [f"Not imported: {e.detail}"]
            continue
        member = members.create_member(db, fund, d, data.scheme_id, data.category_id, data.account_code, checker, request,
                                       joined_reason=f"Joined the fund (bulk upload {batch.filename})")
        if row["values"].get("basic_salary"):
            amount = Decimal(row["values"]["basic_salary"])
            db.add(MemberSalary(member_id=member.id, effective_from=data.date_joined_employer or data.date_joined_fund, basic_salary=amount,
                                pensionable_salary=amount, note="From the bulk upload", approved_by_user_id=checker.id,
                                approval_request_id=request.id))
        row["member_id"] = str(member.id)
        imported += 1
    batch.rows, batch.imported_rows, batch.status = rows, imported, ImportStatus.imported
    db.flush()
    audit.record(db, checker.id, "member_import", batch.id, "imported", after={"imported": imported}, fund_id=batch.fund_id)


def _on_reject(db: Session, request: ApprovalRequest, user: User) -> None:
    batch = db.get(MemberImport, uuid.UUID(request.payload["_import_id"]))
    if batch is not None:
        batch.status = ImportStatus.cancelled if user.id == request.initiated_by_user_id else ImportStatus.rejected


approvals.register(approvals.ApprovalKind(name=KIND, label="Bulk member upload", checker_roles=members.CHECKERS, apply=_apply, on_reject=_on_reject))
