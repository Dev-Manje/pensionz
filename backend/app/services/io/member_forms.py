"""Printable new-member application form (FR-MEM-007) for paper capture.

Blank boxes in the order of the online capture steps, so a member administrator
can key a returned form straight in. When an employer is given, its name, fund
and active categories are printed on the form. Neutral branding (BRAND_* settings)."""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.category import BenefitCategory, CategoryStatus
from app.models.fund import Fund
from app.models.scheme import Scheme

WIDTH = A4[0] - 30 * mm
_styles = getSampleStyleSheet()
TITLE = ParagraphStyle("t", parent=_styles["Title"], fontSize=16, spaceAfter=2, textColor=colors.HexColor(settings.brand_color))
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor(settings.brand_color))
BODY = ParagraphStyle("b", parent=_styles["BodyText"], fontSize=8.5, leading=11)
LABEL = ParagraphStyle("l", parent=BODY, fontSize=7, textColor=colors.HexColor("#555555"))
GRID = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa5ab")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                   ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 12)])


def _boxes(fields: list[str], per_row: int = 3) -> Table:
    """Labelled empty boxes, `per_row` to a line."""
    cells = [Paragraph(f, LABEL) for f in fields]
    while len(cells) % per_row:
        cells.append("")
    rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
    return Table(rows, colWidths=[WIDTH / per_row] * per_row, style=GRID)


def _section(title: str, *flowables) -> KeepTogether:
    return KeepTogether([Paragraph(title, H2), *flowables])


def application_form(db: Session, scheme: Scheme | None) -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title="New member application", author=settings.brand_name)
    story = [Paragraph("New member application", TITLE),
             Paragraph(f"{settings.brand_name} · complete in capital letters and return to {settings.brand_administrator} with a copy of "
                       "your ID. Fields marked * are required.", BODY), Spacer(1, 4)]

    if scheme is not None:
        fund = db.get(Fund, scheme.fund_id)
        categories = db.execute(select(BenefitCategory).where(BenefitCategory.scheme_id == scheme.id, BenefitCategory.status == CategoryStatus.active)
                                .order_by(BenefitCategory.code)).scalars().all()
        story.append(_section("Employer and fund", Table(
            [[Paragraph(f"<b>Fund:</b> {fund.code} — {fund.name}", BODY), Paragraph(f"<b>Employer:</b> {scheme.code} — {scheme.name}", BODY)],
             [Paragraph("<b>Benefit category (tick one):</b> " + "   ".join(f"[  ] {c.code} — {c.name}" for c in categories), BODY), ""]],
            colWidths=[WIDTH / 2] * 2, style=TableStyle([("SPAN", (0, 1), (1, 1)), ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa5ab")),
                                                         ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))))
        story.append(_boxes(["Employee number", "Date joined the employer", "Date joined the fund *"]))
    else:
        story.append(_section("Employer and fund", _boxes(["Fund *", "Employer *", "Benefit category *", "Employee number",
                                                           "Date joined the employer", "Date joined the fund *"])))

    story.append(_section("Personal details", _boxes([
        "Title", "First name *", "Other names", "Last name *", "Maiden name", "Gender (F / M) *", "Date of birth *", "Nationality",
        "Civil status", "ID type", "ID number", "District / village of birth"])))
    story.append(_section("Address and contact", _boxes([
        "Physical address", "Postal address", "Postal district / village", "Home district", "Traditional authority", "Home village",
        "Mobile *", "Telephone", "Email", "Preferred contact (phone / SMS / email / post)"], per_row=2)))
    story.append(_section("Bank account for benefit payments", _boxes(["Bank", "Branch", "Account name", "Account number"], per_row=2)))
    story.append(_section("Next of kin", _boxes(["Name", "Relationship", "Telephone", "Email"], per_row=2)))

    head = [Paragraph(h, LABEL) for h in ("Full name", "Relationship", "Date of birth", "ID number", "Phone", "Share %",
                                          "Guardian (if under 18): name, relationship, phone")]
    widths = [0.19, 0.11, 0.11, 0.12, 0.12, 0.07, 0.28]
    story.append(_section(
        "Beneficiary nomination",
        Paragraph("Shares must add up to 100%. The trustees decide who is paid if you die; your nomination guides them. A guardian is needed for "
                  "anyone under 18.", BODY), Spacer(1, 3),
        Table([head] + [[""] * 7 for _ in range(5)], colWidths=[WIDTH * w for w in widths], rowHeights=[None] + [18] * 5,
              style=TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa5ab")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f4"))])),
    ))
    story.append(_section(
        "Declaration",
        Paragraph("I declare that the information on this form is true and complete. I will tell the administrator of any change. I consent to "
                  "my information being used to administer my membership and shared with the fund's trustees, my employer and regulators as "
                  "the law requires (Data Protection Act).", BODY), Spacer(1, 4),
        _boxes(["Member's signature", "Full name", "Date"]),
        Spacer(1, 4), _boxes(["Employer's authorised signature and stamp", "Name and position", "Date"]),
    ))
    story.append(_section("For office use", _boxes(["Received by / date", "Captured by / date", "Account code"])))
    doc.build(story)
    return out.getvalue()
