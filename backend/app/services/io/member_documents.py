"""Member documents (FR-ENQ-003, FR-ENQ-008), A4 PDF on the fund letterhead used by
the employer statements: Member Benefit Statement (one member, or many — one
page each — for bulk runs), Client Statement, Transaction Trail and the
Contributions / Voluntary Contributions Trails. Data from services/member_statements.py.
"""
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.fund import Fund
from app.models.member import Member
from app.models.scheme import Scheme
from app.services import member_statements as ms
from app.services.io.employer_statements import CELL, CELL_R, SECTION, _amt, _build, _footer, _grid
from app.services.io.receipt_document import BODY, FUND_NAME, LABEL, SMALL, TITLE, WIDTH

COMPONENT_NAMES = {"employee": "Employee", "employer": "Employer", "voluntary": "Voluntary (AVC)", "severance": "Severance",
                   "transfer_in": "Transfer in"}


def _head(db: Session, member: Member, title: str, subtitle: str) -> list:
    fund = db.get(Fund, member.fund_id)
    address = ", ".join(a for a in (fund.address_line1, fund.address_line2, fund.address_line3, fund.address_line4, fund.address_line5) if a)
    contact = " · ".join(x for x in (address, fund.phone, fund.email) if x)
    return [Paragraph(fund.name, FUND_NAME), Paragraph(contact or fund.code, SMALL), Paragraph(title, TITLE), Paragraph(subtitle, BODY),
            Spacer(1, 6)]


def _details(db: Session, member: Member, extra: list[tuple[str, str]] | None = None) -> Table:
    scheme = db.get(Scheme, member.scheme_id) if member.scheme_id else None
    rows = [("Name", member.full_name), ("Member no.", member.account_code),
            ("Employer", f"{scheme.name}" if scheme else "—"), ("Employee no.", member.employee_no or "—"),
            ("Date of birth", f"{member.date_of_birth:%d %B %Y}"), ("Date joined", f"{member.date_joined_fund:%d %B %Y}")]
    rows += extra or []
    pairs = [rows[i:i + 2] for i in range(0, len(rows), 2)]
    data = []
    for p in pairs:
        row = [Paragraph(p[0][0], LABEL), Paragraph(p[0][1], BODY)]
        row += [Paragraph(p[1][0], LABEL), Paragraph(p[1][1], BODY)] if len(p) > 1 else ["", ""]
        data.append(row)
    table = Table(data, colWidths=[WIDTH * w for w in (0.17, 0.33, 0.17, 0.33)])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return table


def _account_table(title: str, lines: list[tuple[str, Decimal]], total: Decimal) -> Table:
    data = [[Paragraph(f"<b>{title}</b>", CELL), ""]]
    data += [[Paragraph(label, CELL), Paragraph(_amt(value), CELL_R)] for label, value in lines]
    data.append([Paragraph(f"<b>Total {title.lower()}</b>", CELL), Paragraph(f"<b>{_amt(total)}</b>", CELL_R)])
    table = Table(data, colWidths=[WIDTH * 0.7, WIDTH * 0.3])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f3")), ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#d5dadd")),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _benefit_story(db: Session, s: ms.BenefitStatement, printed: date) -> list:
    fund = db.get(Fund, s.member.fund_id)
    story = _head(db, s.member, "Member Benefit Statement", f"As at {s.as_at:%d %B %Y}")
    story += [_details(db, s.member), Spacer(1, 10),
              _account_table("Employee account", s.employee_lines, s.employee_total), Spacer(1, 8),
              _account_table("Employer account", s.employer_lines, s.employer_total), Spacer(1, 10)]
    total = Table([[Paragraph("<b>Total benefits for the member (withdrawal / death)</b>", BODY), Paragraph(f"<b>MWK {_amt(s.total)}</b>", CELL_R)]],
                  colWidths=[WIDTH * 0.7, WIDTH * 0.3])
    total.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.black), ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.black),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [total, Spacer(1, 8),
              Paragraph(f"Contributions up to: {s.contributions_up_to:%B %Y}" if s.contributions_up_to else "No contributions credited yet.", BODY),
              Paragraph("The employer account is shown in full; what a leaver may take depends on the vesting scale of the member's "
                        "category and the fund rules at the time of the claim.", SMALL)]
    story += _footer(fund, printed)
    return story


def benefit_statement_pdf(db: Session, member: Member, as_at: date, printed: date) -> bytes:
    return _build(_benefit_story(db, ms.benefit_statement(db, member, as_at), printed), f"Benefit statement {member.account_code}")


def bulk_benefit_statements_pdf(db: Session, members: list[Member], as_at: date, printed: date) -> bytes:
    story: list = []
    for i, member in enumerate(members):
        if i:
            story.append(PageBreak())
        story += _benefit_story(db, ms.benefit_statement(db, member, as_at), printed)
    return _build(story, f"Benefit statements as at {as_at:%d %b %Y}")


def client_statement_pdf(db: Session, member: Member, start: date, end: date, printed: date) -> bytes:
    s = ms.client_statement(db, member, start, end)
    fund = db.get(Fund, member.fund_id)
    story = _head(db, member, "Client Statement", f"{start:%d %B %Y} to {end:%d %B %Y} · statement date {printed:%d %B %Y}")
    address = member.postal_address or member.physical_address
    story += [_details(db, member, [("Address", address)] if address else None), Spacer(1, 8)]
    rows = [[f"{start:%d/%m/%Y}", "Balance brought forward", "", "", "", "", _amt(s.opening)]]
    rows += [[f"{l.transaction_date:%d/%m/%Y}", l.description, l.reference or "", l.transaction, _amt(l.debit) if l.debit else "",
              _amt(l.credit) if l.credit else "", _amt(l.balance)] for l in s.lines]
    story.append(_grid(["Date", "Description", "Reference", "Transaction", "Debit", "Credit", "Balance"], rows,
                       [0.12, 0.23, 0.14, 0.13, 0.126, 0.126, 0.128], {4, 5, 6}, ["", "Current balance", "", "", "", "", _amt(s.closing)]))
    story += [Paragraph("Aged analysis — contributions still owed by the employer", SECTION),
              _grid([label for label, _ in s.ageing], [[_amt(v) for _, v in s.ageing]], [1 / len(s.ageing)] * len(s.ageing), set(range(len(s.ageing))))]
    story += [Spacer(1, 10), Paragraph("Please do not hesitate to contact us if you have any queries.", BODY)]
    story += _footer(fund, printed)
    return _build(story, f"Client statement {member.account_code}")


def transaction_trail_pdf(db: Session, member: Member, start: date, end: date, printed: date) -> bytes:
    t = ms.transaction_trail(db, member, start, end)
    fund = db.get(Fund, member.fund_id)
    story = _head(db, member, "Transaction Trail", f"{start:%d %B %Y} to {end:%d %B %Y}") + [_details(db, member), Spacer(1, 8)]
    rows = [[f"{l.transaction_date:%d/%m/%Y}", l.transaction, l.reference or "", l.description, COMPONENT_NAMES[l.component.value],
             _amt(l.debit) if l.debit else "", _amt(l.credit) if l.credit else ""] for l in t.lines]
    debit, credit = sum((v[0] for v in t.totals.values()), Decimal("0")), sum((v[1] for v in t.totals.values()), Decimal("0"))
    story.append(_grid(["Date", "Type", "Reference", "Description", "Account", "Debit", "Credit"], rows,
                       [0.12, 0.15, 0.14, 0.20, 0.11, 0.14, 0.14], {5, 6}, ["", "", "", "Total", "", _amt(debit), _amt(credit)]))
    story += [Paragraph("Totals per account", SECTION),
              _grid(["Account", "Debit", "Credit", "Net"], [[COMPONENT_NAMES[c.value], _amt(d), _amt(cr), _amt(cr - d)] for c, (d, cr) in t.totals.items()],
                    [0.4, 0.2, 0.2, 0.2], {1, 2, 3})]
    story += _footer(fund, printed)
    return _build(story, f"Transaction trail {member.account_code}")


def contributions_trail_pdf(db: Session, member: Member, start: date, end: date, printed: date, *, voluntary: bool = False) -> bytes:
    months = ms.contributions_trail(db, member, start, end)
    fund = db.get(Fund, member.fund_id)
    title = "Account Voluntary Contributions Trail" if voluntary else "Account Contributions Trail"
    story = _head(db, member, title, f"{start:%B %Y} to {end:%B %Y}") + [_details(db, member), Spacer(1, 8)]
    if voluntary:
        rows = [[f"{m.month:%b %Y}", _amt(m.voluntary), _amt(m.voluntary_earning), _amt(m.voluntary + m.voluntary_earning)]
                for m in months if m.voluntary or m.voluntary_earning]
        story.append(_grid(["Period", "Employee contribution", "Earning", "Total"], rows, [0.25, 0.25, 0.25, 0.25], {1, 2, 3},
                           ["Total", _amt(sum((m.voluntary for m in months), Decimal("0"))), _amt(sum((m.voluntary_earning for m in months), Decimal("0"))),
                            _amt(sum((m.voluntary + m.voluntary_earning for m in months), Decimal("0")))]))
    else:
        rows = [[f"{m.month:%b %Y}", _amt(m.employee), _amt(m.company), _amt(m.employee_earning), _amt(m.company_earning), _amt(m.earning),
                 f"{m.earning_rate.normalize():f}%" if m.earning_rate is not None and m.earning else "", _amt(m.total)] for m in months]
        tot = lambda f: _amt(sum((f(m) for m in months), Decimal("0")))  # noqa: E731
        story.append(_grid(["Period", "Employee contribution", "Company contribution", "Emp. earning", "Comp. earning", "Earning",
                            "Earning rate", "Total"], rows, [0.12, 0.13, 0.13, 0.11, 0.11, 0.11, 0.11, 0.18], {1, 2, 3, 4, 5, 6, 7},
                           ["Total", tot(lambda m: m.employee), tot(lambda m: m.company), tot(lambda m: m.employee_earning),
                            tot(lambda m: m.company_earning), tot(lambda m: m.earning), "", tot(lambda m: m.total)]))
    story += [Spacer(1, 6), Paragraph("Earnings are shown in the month that ends the bonus period they were declared for.", SMALL)]
    story += _footer(fund, printed)
    return _build(story, f"{title} {member.account_code}")

