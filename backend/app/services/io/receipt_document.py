"""Contribution receipt documents (FR-CON-010), two kinds (decided with the user 2026-11-02):

- **Acknowledgement** for a principal officer's payment notice: "received, pending
  confirmation" — it is not a receipt and says so;
- **Official receipt** once staff have confirmed the money in the fund's bank
  account and a checker approved it: receipt number, value date, amount in words.

A4, fund letterhead, neutral product branding (BRAND_* settings)."""
import io
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import settings
from app.models.contribution import ContributionReceipt, ReceiptStatus
from app.models.fund import Fund, FundBankAccount
from app.models.scheme import Scheme
from app.services import periods

WIDTH = A4[0] - 40 * mm
_styles = getSampleStyleSheet()
BRAND = colors.HexColor(settings.brand_color)
FUND_NAME = ParagraphStyle("f", parent=_styles["Title"], fontSize=15, alignment=0, spaceAfter=1, textColor=BRAND)
SMALL = ParagraphStyle("s", parent=_styles["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#555555"))
TITLE = ParagraphStyle("t", parent=_styles["Heading1"], fontSize=17, spaceBefore=10, spaceAfter=2)
BODY = ParagraphStyle("b", parent=_styles["BodyText"], fontSize=10, leading=14)
LABEL = ParagraphStyle("l", parent=BODY, fontSize=8.5, textColor=colors.HexColor("#555555"))
BANNER = ParagraphStyle("w", parent=BODY, fontSize=10, leading=14, textColor=colors.HexColor("#7a4b00"))

PAYMENT_METHODS = {"eft": "EFT", "rtgs": "RTGS", "cheque": "Cheque", "cash_deposit": "Cash deposit", "mobile_money": "Mobile money"}

_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
         "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SCALES = [(10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")]


def _below_thousand(n: int) -> str:
    words = []
    if n >= 100:
        words.append(f"{_ONES[n // 100]} hundred")
        n %= 100
        if n:
            words.append("and")
    if n >= 20:
        words.append(_TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        words.append(_ONES[n])
    return " ".join(words)


def number_words(n: int) -> str:
    if n == 0:
        return "zero"
    parts = []
    for size, name in _SCALES:
        if n >= size:
            parts.append(f"{_below_thousand(n // size)} {name}")
            n %= size
    if n:
        parts.append(("and " if parts and n < 100 else "") + _below_thousand(n))
    return " ".join(parts)


def amount_in_words(amount: Decimal) -> str:
    """1250000.50 → "One million two hundred and fifty thousand kwacha and fifty tambala"."""
    kwacha = int(amount)
    tambala = int((amount - kwacha) * 100)
    text = f"{number_words(kwacha)} kwacha" + (f" and {number_words(tambala)} tambala" if tambala else " only")
    return text[0].upper() + text[1:]


def _money(d: Decimal | None) -> str:
    return f"MWK {d:,.2f}" if d is not None else "—"


def _facts(rows: list[tuple[str, str]]) -> Table:
    table = Table([[Paragraph(k, LABEL), Paragraph(v, BODY)] for k, v in rows], colWidths=[WIDTH * 0.32, WIDTH * 0.68])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d5dadd")),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table


def kind(receipt: ContributionReceipt) -> str | None:
    if receipt.status == ReceiptStatus.confirmed:
        return "receipt"
    if receipt.notice_number and receipt.status in (ReceiptStatus.notified, ReceiptStatus.pending_approval):
        return "acknowledgement"
    return None


def render(fund: Fund, scheme: Scheme | None, account: FundBankAccount | None, receipt: ContributionReceipt, printed: date) -> bytes:
    which = kind(receipt)
    out = io.BytesIO()
    title = f"Receipt {receipt.receipt_number}" if which == "receipt" else f"Acknowledgement {receipt.notice_number}"
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=title, author=settings.brand_name)
    address = ", ".join(a for a in (fund.address_line1, fund.address_line2, fund.address_line3, fund.address_line4, fund.address_line5) if a)
    contact = " · ".join(x for x in (address, fund.phone, fund.email, f"TPIN {fund.tpin}" if fund.tpin else None) if x)
    story = [Paragraph(fund.name, FUND_NAME), Paragraph(contact or fund.code, SMALL)]
    payer = f"{scheme.code} — {scheme.name}" if scheme else (receipt.payer_name or "Unidentified payer")
    month = periods.label(receipt.contribution_month) if receipt.contribution_month else "—"

    if which == "receipt":
        story += [
            Paragraph("Official receipt", TITLE),
            Paragraph(f"Receipt number <b>{receipt.receipt_number}</b> · issued {receipt.confirmed_at:%d %B %Y}", BODY), Spacer(1, 8),
            _facts([
                ("Received from", payer),
                ("Amount", f"<b>{_money(receipt.amount)}</b>"),
                ("Amount in words", amount_in_words(receipt.amount)),
                ("Paid by", PAYMENT_METHODS[receipt.payment_method.value]),
                ("Value date", f"{receipt.value_date:%d %B %Y}"),
                ("Into account", f"{account.bank.name} · {account.account_name}" if account else "—"),
                ("Bank reference", receipt.bank_reference or "—"),
                ("Payer's reference", receipt.payer_reference or "—"),
                ("Contributions for", month),
            ]),
            Spacer(1, 10),
            Paragraph("This receipt confirms that the money above reached the fund's bank account. It is credited to members' accounts "
                      "when the employer's contribution schedule for the month has been checked and allocated.", BODY),
        ]
    else:
        story += [
            Paragraph("Acknowledgement of payment notice", TITLE),
            Paragraph(f"Reference <b>{receipt.notice_number}</b> · notice received {receipt.created_at:%d %B %Y}", BODY), Spacer(1, 6),
            Table([[Paragraph("<b>Received — pending confirmation.</b> This is not a receipt. An official receipt is issued once the "
                              "money is confirmed in the fund's bank account.", BANNER)]], colWidths=[WIDTH],
                  style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdf3e1")),
                                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e3b25c")),
                                    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])),
            Spacer(1, 8),
            _facts([
                ("From", payer),
                ("Amount notified", f"<b>{_money(receipt.notified_amount)}</b>"),
                ("Paid by", PAYMENT_METHODS[receipt.payment_method.value]),
                ("Payment date", f"{receipt.payment_date:%d %B %Y}"),
                ("Payer's reference", receipt.payer_reference or "—"),
                ("Contributions for", month),
            ]),
        ]
    story += [Spacer(1, 18), Paragraph(f"Computer-generated by {settings.brand_name} on behalf of {fund.name}; no signature is required. "
                                       f"Printed {printed:%d %B %Y}.", SMALL)]
    doc.build(story)
    return out.getvalue()
