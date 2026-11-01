"""System-wide lists maintained in Setup (FR-CFG-005, FR-CFG-006, FR-CFG-010),
all through one maker-checker mechanism (FR-CFG-011).

Each list is a `SystemList`: its model, its fields (which also drive the
generic Setup screen — the frontend renders forms and tables from
`describe()`), what must be unique, and any extra rules. Adding or changing
a row is a request (approval kind "list_<name>") that a scheme-setup checker
approves; rows are retired with `active = false`, never deleted.

The approval payload shows readable values (a bank's name rather than its
id, "Yes"/"No", option labels); the raw values travel under "_values"."""
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.identity import User, UserRole
from app.models.reference import (
    AccountType, Bank, BankBranch, Country, District, LedgerBehaviour, ReferenceItem, ReferenceList, TraditionalAuthority,
    TransactionEffect, TransactionType, Village,
)
from app.services import approvals, audit


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    # text | number | boolean | select | ref
    type: str = "text"
    required: bool = False
    max_length: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    options: tuple[tuple[str, str], ...] = ()
    ref: str | None = None  # another list's name, for type "ref"
    help: str | None = None
    locked_on_edit: bool = False
    upper: bool = False
    default: Any = None
    column: bool = True  # shown as a table column


@dataclass
class SystemList:
    name: str
    label: str
    plural: str
    group: str
    description: str
    model: type
    fields: tuple[Field, ...]
    unique: tuple[str, ...]
    order_by: tuple[str, ...] = ("name",)
    title_field: str = "name"
    parent_field: str | None = None  # filter key for child lists (branches of a bank…)
    fixed: dict = field(default_factory=dict)  # column values shared by every row of the list
    validate: Callable[[Session, dict, Any], None] | None = None
    after_apply: Callable[[Session, Any, dict], None] | None = None

    @property
    def kind(self) -> str:
        return f"list_{self.name}"


LISTS: dict[str, SystemList] = {}


def _opts(enum_cls: type[Enum], labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple((e.value, labels.get(e.value, e.value)) for e in enum_cls)


ACTIVE = Field("active", "In use", "boolean", default=True, help="Retired entries stay on old records but can't be chosen for new ones.")


# ---- transaction-type pairing rules


def _validate_transaction_type(db: Session, values: dict, existing: TransactionType | None) -> None:
    reversal = values.get("reversal_code")
    if existing is not None and existing.reversal_code is not None and reversal != existing.reversal_code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Type {existing.code} is paired with {existing.reversal_code}; the pairing can't change")
    if reversal is None:
        return
    if reversal == values["code"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A type can't reverse itself")
    partner = db.execute(select(TransactionType).where(TransactionType.code == reversal)).scalar_one_or_none()
    if partner is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"There is no transaction type {reversal} — add the reversal type first")
    if partner.effect.value == values["effect"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Type {reversal} has the same effect; a reversal must have the opposite effect")
    if partner.reversal_code not in (None, values["code"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Type {reversal} is already the reversal of type {partner.reversal_code}")


def _pair_transaction_type(db: Session, row: TransactionType, values: dict) -> None:
    if row.reversal_code is not None:
        partner = db.execute(select(TransactionType).where(TransactionType.code == row.reversal_code)).scalar_one()
        partner.reversal_code = row.code


def register(spec: SystemList) -> SystemList:
    LISTS[spec.name] = spec
    approvals.register(approvals.ApprovalKind(
        name=spec.kind, label=f"{spec.label} (setup)", checker_roles=frozenset({UserRole.scheme_config_checker}),
        apply=lambda db, request, checker: _apply(db, request, checker),  # _apply is defined further down
    ))
    return spec


register(SystemList(
    "transaction_types", "Transaction type", "Transaction types", "Ledger",
    "Codes for every movement on a member's account, each with the type that reverses it. GL codes follow the proposed chart of accounts.",
    TransactionType,
    (
        Field("code", "Code", "number", required=True, minimum=1, maximum=9999, locked_on_edit=True),
        Field("name", "Description", required=True, max_length=80),
        Field("effect", "Effect on member account", "select", required=True, locked_on_edit=True,
              options=_opts(TransactionEffect, {"credit": "Credit (increases balance)", "debit": "Debit (reduces balance)"})),
        Field("reversal_code", "Reversed by type", "number", minimum=1, maximum=9999, help="The type that undoes this one; it must have the opposite effect."),
        Field("debit_gl_code", "Debit GL account", max_length=20),
        Field("credit_gl_code", "Credit GL account", max_length=20),
        ACTIVE,
    ),
    unique=("code",), order_by=("code",), validate=_validate_transaction_type, after_apply=_pair_transaction_type,
))
register(SystemList(
    "account_types", "Account type", "Account types", "Ledger",
    "Kinds of account in the ledger and how each behaves.",
    AccountType,
    (
        Field("code", "Code", required=True, max_length=10, upper=True, locked_on_edit=True),
        Field("name", "Name", required=True, max_length=80),
        Field("ledger_behaviour", "Behaves as", "select", required=True,
              options=_opts(LedgerBehaviour, {"fund": "Fund account", "member": "Member account", "employer": "Employer account",
                                              "reserve": "Reserve account", "other": "Other"})),
        ACTIVE,
    ),
    unique=("code",), order_by=("code",),
))
register(SystemList(
    "banks", "Bank", "Banks", "Banks",
    "Banks used for fund, member and payee bank accounts.",
    Bank,
    (
        Field("name", "Bank", required=True, max_length=120),
        Field("short_name", "Short name", max_length=30),
        Field("swift_code", "SWIFT / BIC", max_length=11, upper=True),
        Field("sort_order", "List position", "number", minimum=0, maximum=999, default=0, column=False),
        ACTIVE,
    ),
    unique=("name",), order_by=("sort_order", "name"),
))
register(SystemList(
    "bank_branches", "Bank branch", "Bank branches", "Banks",
    "Branches of each bank, with their sort / branch codes.",
    BankBranch,
    (
        Field("bank_id", "Bank", "ref", required=True, ref="banks", locked_on_edit=True),
        Field("name", "Branch", required=True, max_length=120),
        Field("code", "Branch code", max_length=20, upper=True),
        ACTIVE,
    ),
    unique=("bank_id", "name"), parent_field="bank_id",
))
register(SystemList(
    "districts", "District", "Districts", "Places",
    "Malawi's districts, for home, postal and place-of-birth addresses.",
    District,
    (
        Field("name", "District", required=True, max_length=80),
        Field("region", "Region", "select", required=True, options=(("northern", "Northern"), ("central", "Central"), ("southern", "Southern"))),
        ACTIVE,
    ),
    unique=("name",),
))
register(SystemList(
    "traditional_authorities", "Traditional authority", "Traditional authorities", "Places",
    "Traditional authorities (TAs) within each district.",
    TraditionalAuthority,
    (Field("district_id", "District", "ref", required=True, ref="districts", locked_on_edit=True),
     Field("name", "Traditional authority", required=True, max_length=120), ACTIVE),
    unique=("district_id", "name"), parent_field="district_id",
))
register(SystemList(
    "villages", "Village", "Villages", "Places",
    "Villages within each traditional authority.",
    Village,
    (Field("traditional_authority_id", "Traditional authority", "ref", required=True, ref="traditional_authorities", locked_on_edit=True),
     Field("name", "Village", required=True, max_length=120), ACTIVE),
    unique=("traditional_authority_id", "name"), parent_field="traditional_authority_id",
))
register(SystemList(
    "countries", "Country", "Countries", "Places",
    "ISO 3166 countries — also used for nationality.",
    Country,
    (
        Field("code", "ISO code", required=True, max_length=2, upper=True, locked_on_edit=True),
        Field("code3", "ISO 3-letter code", required=True, max_length=3, upper=True, locked_on_edit=True),
        Field("name", "Country", required=True, max_length=120),
        ACTIVE,
    ),
    unique=("code",),
))
for _key, _label, _plural, _desc in (
    (ReferenceList.relationship, "Relationship", "Relationships", "Relationships of beneficiaries, next of kin and guardians to a member."),
    (ReferenceList.id_type, "ID type", "ID types", "Identity documents accepted for KYC."),
    (ReferenceList.permit_type, "Permit type", "Permit types", "Immigration permits held by foreign nationals."),
    (ReferenceList.salutation, "Salutation", "Salutations", "Titles used in letters and statements."),
    (ReferenceList.kyc_product, "KYC product", "KYC products", "Products and schemes an applicant can tick on the KYC form."),
):
    register(SystemList(
        f"{_key.value}s", _label, _plural, "People", _desc, ReferenceItem,
        (
            Field("code", "Code", required=True, max_length=20, upper=True, locked_on_edit=True),
            Field("name", "Name", required=True, max_length=120),
            Field("sort_order", "List position", "number", minimum=0, maximum=999, default=0, column=False),
            ACTIVE,
        ),
        unique=("list_key", "code"), order_by=("sort_order", "name"), fixed={"list_key": _key},
    ))


# ---- reading


def get_list(name: str) -> SystemList:
    if name not in LISTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown list")
    return LISTS[name]


def describe() -> list[dict]:
    """The lists and their fields, for the generic Setup screen."""
    return [
        {
            "name": s.name, "label": s.label, "plural": s.plural, "group": s.group, "description": s.description,
            "parent_field": s.parent_field,
            "fields": [
                {"name": f.name, "label": f.label, "type": f.type, "required": f.required, "max_length": f.max_length,
                 "minimum": f.minimum, "maximum": f.maximum, "options": [{"value": v, "label": lbl} for v, lbl in f.options],
                 "ref": f.ref, "help": f.help, "locked_on_edit": f.locked_on_edit, "upper": f.upper, "default": f.default,
                 "column": f.column}
                for f in s.fields
            ],
        }
        for s in LISTS.values()
    ]


def _query(spec: SystemList):
    query = select(spec.model)
    for key, value in spec.fixed.items():
        query = query.where(getattr(spec.model, key) == value)
    return query


def _title(db: Session, list_name: str, row_id) -> str | None:
    if not row_id:
        return None
    spec = LISTS[list_name]
    row = db.get(spec.model, uuid.UUID(str(row_id)))
    return getattr(row, spec.title_field) if row is not None else None


def pending_request_id(db: Session, spec: SystemList, row_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == spec.kind, ApprovalRequest.entity_id == str(row_id), ApprovalRequest.status == ApprovalStatus.pending,
        )
    ).scalar_one_or_none()


def rows(db: Session, spec: SystemList, parent: uuid.UUID | None = None) -> list[dict]:
    query = _query(spec)
    if parent is not None and spec.parent_field:
        query = query.where(getattr(spec.model, spec.parent_field) == parent)
    query = query.order_by(*[getattr(spec.model, f) for f in spec.order_by])
    result = []
    pending = dict(db.execute(
        select(ApprovalRequest.entity_id, ApprovalRequest.id).where(ApprovalRequest.kind == spec.kind, ApprovalRequest.status == ApprovalStatus.pending)
    ).all())
    ref_titles: dict[tuple[str, str], str | None] = {}
    for row in db.execute(query).scalars():
        out = {"id": str(row.id), "pending_approval_id": str(pending[str(row.id)]) if str(row.id) in pending else None}
        for f in spec.fields:
            value = audit._jsonable(getattr(row, f.name))
            out[f.name] = value
            if f.type == "ref":
                key = (f.ref, value)
                if key not in ref_titles:
                    ref_titles[key] = _title(db, f.ref, value)
                out[f"{f.name}_label"] = ref_titles[key]
        result.append(out)
    return result


# ---- proposing


def _clean(db: Session, spec: SystemList, data: dict, existing) -> dict:
    values = {}
    for f in spec.fields:
        value = data.get(f.name, f.default if existing is None else audit._jsonable(getattr(existing, f.name)))
        if existing is not None and f.locked_on_edit:
            current = audit._jsonable(getattr(existing, f.name))
            if value is not None and str(value) != str(current):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.label} can't change once set")
            value = current
        if isinstance(value, str):
            value = value.strip() or None
            if value is not None and f.upper:
                value = value.upper()
        if value is None:
            if f.required:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.label} is required")
            values[f.name] = None
            continue
        if f.type == "number":
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.label} must be a whole number")
            if (f.minimum is not None and value < f.minimum) or (f.maximum is not None and value > f.maximum):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.label} must be between {f.minimum} and {f.maximum}")
        elif f.type == "boolean":
            value = bool(value)
        elif f.type == "select":
            if value not in [v for v, _ in f.options]:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Choose a {f.label.lower()} from the list")
        elif f.type == "ref":
            if _title(db, f.ref, value) is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Choose a {f.label.lower()} from the list")
            value = str(value)
        elif f.max_length and len(str(value)) > f.max_length:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.label} can be at most {f.max_length} characters")
        values[f.name] = value
    return values


def _check_unique(db: Session, spec: SystemList, values: dict, row_id: uuid.UUID | None, ignore_request: uuid.UUID | None = None) -> None:
    query = _query(spec)
    types = {f.name: f.type for f in spec.fields}
    for key in spec.unique:
        if key in spec.fixed:
            continue
        column, value = getattr(spec.model, key), values[key]
        if types[key] == "ref":
            query = query.where(column == uuid.UUID(str(value)))
        elif isinstance(value, str):
            query = query.where(func.upper(column) == value.upper())  # "Lilongwe" clashes with "LILONGWE"
        else:
            query = query.where(column == value)
    clash = db.execute(query).scalars().first()
    labels = " / ".join(next(f.label for f in spec.fields if f.name == k) for k in spec.unique if k not in spec.fixed)
    if clash is not None and clash.id != row_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"There is already a {spec.label.lower()} with that {labels.lower()}")
    for request in db.execute(
        select(ApprovalRequest).where(ApprovalRequest.kind == spec.kind, ApprovalRequest.status == ApprovalStatus.pending)
    ).scalars():
        theirs = request.payload.get("_values", {})
        same_key = all(str(theirs.get(k)).upper() == str(values[k]).upper() for k in spec.unique if k not in spec.fixed)
        same_row = row_id is not None and request.entity_id == str(row_id)
        if same_key and not same_row and request.id != ignore_request:
            raise HTTPException(status.HTTP_409_CONFLICT, f"A {spec.label.lower()} with that {labels.lower()} is already waiting for approval")


def _readable(db: Session, spec: SystemList, values: dict) -> dict:
    out = {}
    for f in spec.fields:
        value = values.get(f.name)
        if f.type == "boolean":
            value = "Yes" if value else "No"
        elif f.type == "select" and value is not None:
            value = dict(f.options).get(value, value)
        elif f.type == "ref":
            value = _title(db, f.ref, value)
        out[f.name] = value
    return out


def propose(db: Session, maker: User, spec: SystemList, data: dict, row=None) -> ApprovalRequest:
    values = _clean(db, spec, data, row)
    if spec.validate:
        spec.validate(db, values, row)
    if row is not None:
        current = {f.name: audit._jsonable(getattr(row, f.name)) for f in spec.fields}
        changed = [f.label.lower() for f in spec.fields if str(values[f.name]) != str(current[f.name])]
        if not changed:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing has changed")
    _check_unique(db, spec, values, row.id if row is not None else None)
    title = values.get(spec.title_field) or values.get("code")
    if row is None:
        summary = f"New {spec.label.lower()}: {title}"
    else:
        summary = f"Change {spec.label.lower()} {getattr(row, spec.title_field)}: {', '.join(changed)}"
    request = approvals.submit(
        db, maker, spec.kind, entity_type=spec.model.__tablename__, entity_id=row.id if row is not None else None,
        summary=summary[:300],
        payload={"action": "update" if row is not None else "create", **_readable(db, spec, values), "_values": values},
        previous=_readable(db, spec, {f.name: audit._jsonable(getattr(row, f.name)) for f in spec.fields}) if row is not None else None,
    )
    db.commit()
    db.refresh(request)
    return request


def _to_columns(spec: SystemList, values: dict) -> dict:
    out = {}
    for f in spec.fields:
        value = values[f.name]
        if f.type == "ref" and value is not None:
            value = uuid.UUID(value)
        out[f.name] = value
    return {**out, **spec.fixed}


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    spec = next(s for s in LISTS.values() if s.kind == request.kind)
    values = request.payload["_values"]
    row = None
    if request.payload["action"] == "update":
        row = db.execute(select(spec.model).where(spec.model.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"That {spec.label.lower()} no longer exists")
    if spec.validate:
        spec.validate(db, values, row)
    _check_unique(db, spec, values, row.id if row is not None else None, ignore_request=request.id)
    before = {f.name: audit._jsonable(getattr(row, f.name)) for f in spec.fields} if row is not None else None
    if row is None:
        row = spec.model(**_to_columns(spec, values))
        db.add(row)
    else:
        for key, value in _to_columns(spec, values).items():
            setattr(row, key, value)
    db.flush()
    if spec.after_apply:
        spec.after_apply(db, row, values)
    request.entity_id = str(row.id)
    audit.record(db, checker.id, spec.model.__tablename__, row.id, "updated" if before else "created", before=before, after=values)
