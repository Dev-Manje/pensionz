"""What each KYC form asks for (source: "kyc Requirements.docx", REQUIREMENTS
FR-ONB-C*/G*/I*), how a submission is checked, and the risk rules.

`requirements(client_type, data)` lists the documents the application needs —
some repeat per director / signatory, some only apply to foreign residents.
`problems(client_type, data, documents)` returns every reason the application
can't be submitted yet, so the form can show them all at once.
Every document list ends with "other", which needs a description."""
from dataclasses import dataclass, field
from datetime import date

from app.models.kyc import ClientType, KycDocument, RiskRating

OTHER = ("other", "Other (type it)")


@dataclass(frozen=True)
class DocType:
    code: str
    label: str
    # Freshness rule: the document must be issued within this many months.
    max_age_months: int | None = None


@dataclass(frozen=True)
class Requirement:
    key: str
    label: str
    types: tuple[DocType, ...]
    issue_date: bool = True
    expiry_date: bool = False
    help: str | None = None
    # "directors" / "signatories": one per person in that list.
    per: str | None = None
    # Only for people who are foreign nationals resident in Malawi.
    foreign_only: bool = False


def _types(*items) -> tuple[DocType, ...]:
    return tuple(DocType(*i) if isinstance(i, tuple) else i for i in items) + (DocType(*OTHER),)


PERSON_ID = _types(("national_id", "National ID"), ("passport", "Passport"), ("driving_licence", "Driving licence"))
PERMIT = _types(("employment", "Employment permit"), ("study", "Study permit"), ("temporary_residence", "Temporary residence permit"),
                ("business_residence", "Business residence permit"), ("permanent_residence", "Permanent residence permit"),
                ("diplomatic", "Diplomatic"), ("technical_assistance", "Technical assistance"))
SOURCE_OF_FUNDS = Requirement(
    "source_of_funds", "Source of funds",
    _types(("bank_statements", "Bank statements (at least 3 months)"), ("audited_financials", "Latest audited financial statements"),
           ("tax_returns", "Income tax returns")),
)
PROOF_OF_BANK = Requirement(
    "proof_of_bank_account", "Proof of bank account",
    _types(("bank_statement", "Bank statement"), ("bank_letter", "Bank confirmation letter"), ("deposit_slip", "Deposit slip"),
           ("cancelled_cheque", "Cancelled cheque"), ("transfer_slip", "MO626 or other transfer slip")),
)

REQUIREMENTS: dict[ClientType, tuple[Requirement, ...]] = {
    ClientType.corporate: (
        Requirement("identification", "Identification document",
                    _types(("registration_certificate", "Business registration certificate"),
                           ("incorporation_certificate", "Certificate of incorporation"), ("act_of_parliament", "Act of Parliament"))),
        Requirement("proof_of_address", "Proof of physical address",
                    _types(("landline_bill", "Landline telephone bill (last 3 months)", 3), ("utility_bill", "Utility bill (last 3 months)", 3),
                           ("lease_or_sale", "Lease or sale agreement"), ("city_rates", "City rates (last 12 months)", 12))),
        Requirement("supporting_document", "Supporting document",
                    _types(("articles", "Articles of association"), ("constitution", "Constitution"),
                           ("partnership_agreement", "Partnership agreement"), ("mou_resolution", "MoU or board resolution"))),
        Requirement("director_id", "ID", PERSON_ID, expiry_date=True, per="directors"),
        Requirement("director_permit", "Immigration permit", PERMIT, expiry_date=True, per="directors", foreign_only=True),
        SOURCE_OF_FUNDS,
        PROOF_OF_BANK,
    ),
    ClientType.group: (
        Requirement("founding_document", "Founding document", _types(("constitution", "Constitution"), ("minutes", "Minutes"))),
        SOURCE_OF_FUNDS,
        PROOF_OF_BANK,
        Requirement("signatory_id", "ID", PERSON_ID, expiry_date=True, per="signatories"),
        Requirement("signatory_permit", "Immigration permit", PERMIT, expiry_date=True, per="signatories", foreign_only=True),
        Requirement("signatory_address", "Proof of physical address",
                    _types(("utility_bill", "Utility bill (last 3 months)", 3), ("city_rates", "City rates (last 12 months)", 12),
                           ("lease_agreement", "Lease agreement")), per="signatories"),
    ),
    ClientType.individual: (
        Requirement("identity_document", "Identity document", PERSON_ID, expiry_date=True),
        Requirement("proof_of_address", "Proof of address",
                    _types(("water_bill", "Water bill (last 3 months)", 3), ("electricity_bill", "Electricity bill (last 3 months)", 3),
                           ("city_rates", "City rates (last 12 months)", 12), ("lease_agreement", "Lease agreement"))),
        Requirement("immigration_permit", "Immigration permit", PERMIT, expiry_date=True, foreign_only=True),
    ),
}

ENTITY_FORMS = (("plc", "Public limited company"), ("private_ltd", "Private limited company"), ("ngo", "NGO"),
                ("trust", "Trust"), ("sole_trader", "Sole trader"), OTHER)
GROUP_KINDS = (("village_bank", "Village bank"), ("family_group", "Family group"), ("club", "Club"), ("association", "Association"), OTHER)
MARITAL = (("single", "Single"), ("married", "Married"), ("divorced", "Divorced"), ("widowed", "Widow / widower"))
CONTACT_MODES = (("phone", "Phone call"), ("sms", "SMS"), ("email", "Email"), ("post", "Post"))
GENDERS = (("female", "Female"), ("male", "Male"))
INCOME_SOURCES = (("employment", "Employment"), ("business", "Business"))

PEP_DEFINITION = (
    "A politically exposed person (PEP) is someone who holds, or has held in the last year, a prominent public "
    "function — for example a head of state or government, minister, member of parliament, senior judge, senior "
    "military or police officer, senior official of a state-owned enterprise or political party — or is a close "
    "family member or known close associate of such a person. A politically exposed entity is one owned or "
    "controlled by such a person."
)


PERSON_WORD = {"directors": "Director", "signatories": "Signatory"}


@dataclass
class Slot:
    """One document the application needs, e.g. "director_id:1" for the second director."""

    key: str
    requirement: Requirement
    label: str
    person: str | None = None
    extras: dict = field(default_factory=dict)


def _people(client_type: ClientType, data: dict) -> dict[str, list[dict]]:
    return {"directors": data.get("directors") or [], "signatories": data.get("signatories") or []}


def is_foreign_resident(person: dict) -> bool:
    """A foreign national living in Malawi (needs an immigration permit). Individuals give
    their country of residence; directors and signatories answer "resident in Malawi"."""
    if not person.get("nationality") or person.get("nationality") == "MW":
        return False
    if "country_of_residence" in person:
        return person.get("country_of_residence") == "MW"
    return bool(person.get("resident_in_malawi", True))


def slots(client_type: ClientType, data: dict) -> list[Slot]:
    out = []
    people = _people(client_type, data)
    for req in REQUIREMENTS[client_type]:
        if req.per:
            for i, person in enumerate(people[req.per]):
                if req.foreign_only and not is_foreign_resident(person):
                    continue
                name = person.get("full_name") or f"{PERSON_WORD[req.per]} {i + 1}"
                out.append(Slot(f"{req.key}:{i}", req, f"{req.label} — {name}", person=name))
        else:
            if req.foreign_only and not (client_type == ClientType.individual and is_foreign_resident(data)):
                continue
            out.append(Slot(req.key, req, req.label))
    return out


def _months_between(earlier: date, later: date) -> float:
    return (later - earlier).days / 30.44


def document_problems(slot: Slot, doc: KycDocument | None, today: date) -> list[str]:
    if doc is None:
        return [f"Upload the {slot.label.lower()}"]
    problems = []
    codes = {t.code: t for t in slot.requirement.types}
    doc_type = codes.get(doc.doc_type)
    if doc_type is None:
        problems.append(f"{slot.label}: choose the document type from the list")
    elif doc.doc_type == "other" and not doc.doc_type_other:
        problems.append(f"{slot.label}: say what the document is")
    if slot.requirement.issue_date and not doc.issue_date:
        problems.append(f"{slot.label}: give the issue date")
    if doc_type and doc_type.max_age_months and doc.issue_date and _months_between(doc.issue_date, today) > doc_type.max_age_months:
        problems.append(f"{slot.label}: must be issued within the last {doc_type.max_age_months} months")
    if slot.requirement.expiry_date and doc.expiry_date and doc.expiry_date < today:
        problems.append(f"{slot.label}: has expired")
    return problems


REQUIRED_FIELDS: dict[ClientType, tuple[tuple[str, str], ...]] = {
    ClientType.corporate: (
        ("entity_name", "Organisation name"), ("entity_form", "Type of organisation"), ("registration_number", "Registration number"),
        ("office_phone", "Office phone"), ("email", "Email"), ("physical_address", "Physical address"),
        ("contact_name", "Contact person's name"), ("contact_phone", "Contact person's phone"), ("contact_email", "Contact person's email"),
    ),
    ClientType.group: (
        ("group_name", "Group name"), ("group_kind", "Type of group"), ("phone", "Phone"), ("physical_address", "Physical address"),
    ),
    ClientType.individual: (
        ("first_name", "First name"), ("last_name", "Last name"), ("gender", "Gender"), ("marital_status", "Marital status"),
        ("date_of_birth", "Date of birth"), ("id_type", "ID type"), ("id_number", "ID number"),
        ("physical_address", "Physical address"), ("nationality", "Nationality"), ("country_of_residence", "Country of residence"),
        ("mobile", "Mobile number"), ("preferred_contact", "Preferred way to contact you"), ("income_source", "Source of income"),
        ("source_of_funds", "Source of funds"),
    ),
}


def display_name(client_type: ClientType, data: dict) -> str:
    if client_type == ClientType.corporate:
        return (data.get("entity_name") or "").strip()
    if client_type == ClientType.group:
        return (data.get("group_name") or "").strip()
    return " ".join(p for p in (data.get("first_name"), data.get("middle_name"), data.get("last_name")) if p).strip()


def identifier(client_type: ClientType, data: dict) -> str | None:
    return data.get("registration_number") if client_type == ClientType.corporate else data.get("id_number")


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def problems(client_type: ClientType, data: dict, documents: list[KycDocument], today: date) -> list[str]:
    """Everything stopping the application from being submitted."""
    out = [f"{label} is required" for key, label in REQUIRED_FIELDS[client_type] if _blank(data.get(key))]
    for key, options in (("entity_form", ENTITY_FORMS), ("group_kind", GROUP_KINDS)):
        if data.get(key) == "other" and _blank(data.get(f"{key}_other")):
            out.append("Say what type of organisation or group it is")
    if client_type == ClientType.corporate and data.get("is_pep") is None:
        out.append("Answer whether the organisation is a politically exposed entity")
    if client_type == ClientType.corporate and not data.get("directors"):
        out.append("Add at least one director or senior manager")
    if client_type == ClientType.group:
        signatories = data.get("signatories") or []
        if not signatories:
            out.append("Add at least one signatory")
        for i, s in enumerate(signatories, start=1):
            for key, label in (("full_name", "full name"), ("address", "address"), ("phone", "phone"), ("occupation", "occupation")):
                if _blank(s.get(key)):
                    out.append(f"Signatory {i}: {label} is required")
            if s.get("is_pep") is None:
                out.append(f"Signatory {i}: answer the politically exposed person question")
    if client_type == ClientType.corporate:
        for i, d in enumerate(data.get("directors") or [], start=1):
            for key, label in (("full_name", "full name"), ("position", "position"), ("nationality", "nationality")):
                if _blank(d.get(key)):
                    out.append(f"Director {i}: {label} is required")
    if client_type == ClientType.individual:
        if data.get("is_pep") is None or data.get("related_to_pep") is None:
            out.append("Answer both politically exposed person questions")
        if data.get("income_source") == "employment" and _blank(data.get("employer_name")):
            out.append("Employer name is required")
        if data.get("income_source") == "business" and _blank(data.get("business_type")):
            out.append("Type of business is required")
        if is_foreign_resident(data) and _blank(data.get("permit_type")):
            out.append("Immigration permit type is required for foreign nationals")
        dob = data.get("date_of_birth")
        if dob:
            try:
                if date.fromisoformat(dob) >= today:
                    out.append("Date of birth must be in the past")
            except ValueError:
                out.append("Date of birth isn't a valid date")
        kin = data.get("next_of_kin") or {}
        if _blank(kin.get("name")) or _blank(kin.get("relationship")):
            out.append("Next of kin: name and relationship are required")

    current = {d.requirement: d for d in documents if not d.superseded}
    for slot in slots(client_type, data):
        out += document_problems(slot, current.get(slot.key), today)
    return out


def risk(client_type: ClientType, data: dict) -> tuple[RiskRating, list[str]]:
    """Rule-based rating (FR-ONB-103; rules to confirm with compliance)."""
    high, medium = [], []
    if data.get("is_pep"):
        high.append("The client declared a politically exposed person / entity")
    if data.get("related_to_pep"):
        high.append("The client is related to a politically exposed person")
    for role, people in (("Director", data.get("directors") or []), ("Signatory", data.get("signatories") or [])):
        for p in people:
            if p.get("is_pep"):
                high.append(f"{role} {p.get('full_name') or ''} is a politically exposed person".replace("  ", " "))
            if is_foreign_resident(p):
                medium.append(f"{role} {p.get('full_name') or ''} is a foreign national".replace("  ", " "))
    if client_type == ClientType.group:
        medium.append("Unregistered group")
    if client_type == ClientType.individual and is_foreign_resident(data):
        medium.append("Foreign national")
    if client_type == ClientType.individual and data.get("income_source") == "business":
        medium.append("Business income (possibly cash-based)")
    if high:
        return RiskRating.high, high + medium
    if medium:
        return RiskRating.medium, medium
    return RiskRating.low, []
