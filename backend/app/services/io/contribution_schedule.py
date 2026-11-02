"""Contribution schedule template and reader (FR-CON-003).

The template is prefilled with the employer's active members and their
expected contributions for the month (salary on record × category rates), so
an employer usually only corrects the exceptions. Reading accepts the
template's own .xlsx or a .csv with the same headings."""
import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, status
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
SHEET = "Schedule"


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    required: bool
    width: int
    help: str


COLUMNS = [
    Column("account_code", "Account code", True, 16, "The member's account code (prefilled)."),
    Column("employee_no", "Employee no", False, 14, "Your payroll number for the employee — used when the account code is blank."),
    Column("member_name", "Member name", False, 30, "For your reference; not used to match the member."),
    Column("pensionable_salary", "Pensionable salary", False, 18, "Monthly pensionable salary used for the contributions."),
    Column("employee", "Employee contribution", False, 18, "Deducted from the employee's pay (MWK)."),
    Column("employer", "Employer contribution", False, 18, "Paid by the employer (MWK)."),
    Column("voluntary", "Voluntary (AVC)", False, 16, "Additional voluntary contributions by the employee, if any."),
    Column("severance", "Severance", False, 14, "Severance allowance paid into the fund, if any."),
]
BY_LABEL = {c.label.lower(): c for c in COLUMNS}
MONEY_KEYS = ("pensionable_salary", "employee", "employer", "voluntary", "severance")


def label(key: str) -> str:
    return next(c.label for c in COLUMNS if c.key == key)


def _bad(message: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, message)


def template(title: str, month: date, rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    head_fill, req_fill = PatternFill("solid", fgColor="DCE9EC"), PatternFill("solid", fgColor="F6D7B0")
    for i, col in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=i, value=col.label + (" *" if col.required else ""))
        cell.font, cell.fill = Font(bold=True), req_fill if col.required else head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(i)].width = col.width
    for r in rows:
        ws.append([r.get(c.key) if c.key not in MONEY_KEYS or r.get(c.key) is None else float(r[c.key]) for c in COLUMNS])
    for row in ws.iter_rows(min_row=2, min_col=4, max_col=len(COLUMNS)):
        for cell in row:
            cell.number_format = "#,##0.00"
    ws.freeze_panes = "A2"

    guide = wb.create_sheet("Guide")
    guide["A1"] = f"Contribution schedule — {title} — {month:%B %Y}"
    guide["A1"].font = Font(bold=True, size=13)
    guide["A2"] = ("One row per member. The sheet is prefilled with your active members and the contributions we expect from "
                   "their salary on record — change any that differ and add members who are missing. Don't rename the headings.")
    guide.append([])
    guide.append(["Column", "Required", "What to enter"])
    for c in guide[4]:
        c.font = Font(bold=True)
    for col in COLUMNS:
        guide.append([col.label, "Yes" if col.required else "", col.help])
    guide.column_dimensions["A"].width, guide.column_dimensions["B"].width, guide.column_dimensions["C"].width = 24, 10, 90
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def parse_money(v) -> Decimal | None:
    """Blank → None; "1,250.5" / 1250.5 → Decimal; anything else raises ValueError."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        d = Decimal(str(v).replace(",", "").replace("MWK", "").strip())
    except InvalidOperation:
        raise ValueError(f"“{v}” isn't an amount")
    if not d.is_finite():
        raise ValueError(f"“{v}” isn't an amount")
    return d


def read(filename: str, content: bytes) -> list[tuple[int, dict]]:
    """[(spreadsheet row number, {key: raw value})] for non-blank rows."""
    if len(content) > MAX_BYTES:
        raise _bad("The file is larger than 5 MB — split it into smaller files")
    name = (filename or "").lower()
    if name.endswith(".csv"):
        table = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))
    elif name.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            raise _bad("That file couldn't be read as an Excel workbook (.xlsx)")
        ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        raise _bad("Upload the schedule as .xlsx (or .csv)")
    if not table:
        raise _bad("The file is empty")
    header = [str(h or "").replace("*", "").strip().lower() for h in table[0]]
    keys = [BY_LABEL[h].key if h in BY_LABEL else None for h in header]
    missing = [c.label for c in COLUMNS if c.required and c.key not in keys]
    if missing:
        raise _bad(f"These columns are missing: {', '.join(missing)}. Use the template and keep its headings.")
    if not any(k in keys for k in ("employee", "employer", "voluntary", "severance")):
        raise _bad("The file has no contribution columns — use the template")
    rows = []
    for n, raw in enumerate(table[1:], start=2):
        values = {k: v for k, v in zip(keys, raw) if k}
        if all(v is None or str(v).strip() == "" for v in values.values()):
            continue
        rows.append((n, {k: (_text(v) if k not in MONEY_KEYS else v) for k, v in values.items()}))
    if not rows:
        raise _bad("There are no members in the file")
    if len(rows) > MAX_ROWS:
        raise _bad(f"Up to {MAX_ROWS} rows per file — this one has {len(rows)}")
    return rows
