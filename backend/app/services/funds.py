"""Fund setup (FR-CFG-001) through maker-checker (FR-CFG-011, FR-SEC-002).

A scheme-setup maker sends the whole fund — details, trustees and bank
accounts — as one snapshot; a scheme-setup checker approves it and only then is
it written. Trustees and bank accounts that drop out of the snapshot are kept
inactive (receipts and payments will reference bank accounts), never deleted.
Code and fund type can't change once the fund has members."""
import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.fund import BankAccountPurpose, Fund, FundBankAccount, FundStatus, FundTrustee, FundType
from app.models.identity import User, UserRole
from app.models.reference import Bank, BankBranch
from app.schemas.fund import FundIn
from app.services import approvals, audit, fund_access

KIND = "fund_setup"

FUND_FIELDS = (
    "code", "name", "fund_type", "status", "registration_number", "tpin", "financial_year_end_month",
    "address_line1", "address_line2", "address_line3", "address_line4", "address_line5",
    "phone", "fax", "email", "website",
    "contact_name", "contact_email", "contact_phone", "contact_alt_phone",
)
TRUSTEE_FIELDS = ("full_name", "designation", "email", "phone", "appointed_on")
ACCOUNT_FIELDS = ("bank_id", "branch_id", "account_name", "account_number", "currency", "purpose")
# Changing these after members join would re-label every member's history.
LOCKED_ONCE_MEMBERS = ("code", "fund_type")

TYPE_LABELS = {
    FundType.standalone_dc: "Stand-alone DC",
    FundType.umbrella_dc: "Umbrella DC",
    FundType.personal_pension: "Personal pension",
    FundType.defined_benefit: "Defined benefit",
    FundType.minors_trust: "Minors' trust",
}


def fund_has_members(db: Session, fund: Fund) -> bool:
    from app.services.members import has_members

    return has_members(db, fund.id)


def locked_fields(db: Session, fund: Fund) -> list[str]:
    return list(LOCKED_ONCE_MEMBERS) if fund_has_members(db, fund) else []


def mask_account_number(number: str) -> str:
    return f"•••• {number[-4:]}" if len(number) > 4 else "••••"


def pending_request_id(db: Session, fund_id: uuid.UUID) -> uuid.UUID | None:
    return db.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.kind == KIND,
            ApprovalRequest.entity_id == str(fund_id),
            ApprovalRequest.status == ApprovalStatus.pending,
        )
    ).scalar_one_or_none()


# ---- snapshots: the same shape for "now" and "after approval", so the checker's diff lines up


def _trustee_snapshot(t: FundTrustee) -> dict:
    return {"id": str(t.id), **{f: getattr(t, f) for f in TRUSTEE_FIELDS}}


def _account_snapshot(a: FundBankAccount) -> dict:
    return {
        "id": str(a.id),
        **{f: getattr(a, f) for f in ACCOUNT_FIELDS},
        "bank_name": a.bank.name if a.bank else None,
        "branch_name": a.branch.name if a.branch else None,
    }


def snapshot(fund: Fund) -> dict:
    return audit._jsonable({
        **{f: getattr(fund, f) for f in FUND_FIELDS},
        "trustees": [_trustee_snapshot(t) for t in fund.trustees if t.active],
        "bank_accounts": [_account_snapshot(a) for a in fund.bank_accounts if a.active],
    })


def _proposed(db: Session, data: FundIn, fund: Fund | None) -> dict:
    """Validates the maker's snapshot against the database and returns it in snapshot form."""
    own_trustees = {t.id for t in fund.trustees} if fund else set()
    own_accounts = {a.id: a for a in fund.bank_accounts} if fund else {}

    trustees = []
    for t in data.trustees:
        if t.id is not None and t.id not in own_trustees:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Trustee {t.full_name} doesn't belong to this fund")
        trustees.append({"id": str(t.id) if t.id else None, **t.model_dump(include=set(TRUSTEE_FIELDS))})

    accounts, seen = [], set()
    for a in data.bank_accounts:
        if a.id is not None and a.id not in own_accounts:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Bank account {mask_account_number(a.account_number)} doesn't belong to this fund")
        bank = db.get(Bank, a.bank_id)
        if bank is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a bank from the list")
        existing = own_accounts.get(a.id) if a.id else None
        if not bank.active and (existing is None or existing.bank_id != bank.id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{bank.name} is no longer in use — choose another bank")
        branch = db.get(BankBranch, a.branch_id) if a.branch_id else None
        if a.branch_id and (branch is None or branch.bank_id != bank.id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"That branch isn't a {bank.name} branch")
        key = (a.bank_id, a.account_number)
        if key in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Bank account {a.account_number} is listed twice")
        seen.add(key)
        accounts.append({
            "id": str(a.id) if a.id else None,
            **a.model_dump(include=set(ACCOUNT_FIELDS)),
            "bank_name": bank.name,
            "branch_name": branch.name if branch else None,
        })

    return audit._jsonable({
        **data.model_dump(include=set(FUND_FIELDS)),
        "trustees": trustees,
        "bank_accounts": accounts,
    })


def _check_code_free(db: Session, code: str, fund_id: uuid.UUID | None, ignore_request: uuid.UUID | None = None) -> None:
    taken = db.execute(select(Fund.id).where(func.upper(Fund.code) == code.upper())).scalar_one_or_none()
    if taken is not None and taken != fund_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Fund code {code} is already used by another fund")
    # Another fund waiting for approval may have claimed it too.
    waiting = db.execute(
        select(ApprovalRequest.id, ApprovalRequest.entity_id).where(
            ApprovalRequest.kind == KIND,
            ApprovalRequest.status == ApprovalStatus.pending,
            func.upper(ApprovalRequest.payload["code"].astext) == code.upper(),
        )
    ).all()
    for request_id, entity_id in waiting:
        same_fund = fund_id is not None and entity_id == str(fund_id)
        if request_id != ignore_request and not same_fund:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Fund code {code} is already used by a fund waiting for approval")


def propose_new(db: Session, maker: User, data: FundIn) -> ApprovalRequest:
    if data.status != FundStatus.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A new fund starts as active")
    if any(t.id for t in data.trustees) or any(a.id for a in data.bank_accounts):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A new fund can't refer to existing trustees or bank accounts")
    _check_code_free(db, data.code, None)
    proposed = _proposed(db, data, None)
    request = approvals.submit(
        db, maker, KIND, entity_type="fund", entity_id=None,
        summary=f"New fund {data.code} — {data.name} ({TYPE_LABELS[data.fund_type]})",
        payload={"action": "create", **proposed},
    )
    db.commit()
    db.refresh(request)
    return request


def propose_update(db: Session, maker: User, fund: Fund, data: FundIn) -> ApprovalRequest:
    current = snapshot(fund)
    proposed = _proposed(db, data, fund)
    changed = [k for k in proposed if proposed[k] != current.get(k)]
    if not changed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing has changed")
    frozen = [k for k in locked_fields(db, fund) if k in changed]
    if frozen:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The fund has members, so its {' and '.join(f.replace('_', ' ') for f in frozen)} can't change")
    if "code" in changed:
        _check_code_free(db, data.code, fund.id)
    request = approvals.submit(
        db, maker, KIND, entity_type="fund", entity_id=fund.id,
        summary=f"Change fund {fund.code}: {', '.join(k.replace('_', ' ') for k in changed)}"[:300],
        payload={"action": "update", **proposed},
        previous=current,
        fund_id=fund.id,
    )
    db.commit()
    db.refresh(request)
    return request


def _uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


def _fund_values(data: dict) -> dict:
    values = {f: data.get(f) for f in FUND_FIELDS}
    values["fund_type"] = FundType(values["fund_type"])
    values["status"] = FundStatus(values["status"])
    return values


def _sync_children(db: Session, fund: Fund, data: dict) -> None:
    by_id = {t.id: t for t in fund.trustees}
    keep = set()
    for order, t in enumerate(data["trustees"]):
        row = by_id.get(_uuid(t["id"])) if t.get("id") else None
        if row is None:
            row = FundTrustee(id=uuid.uuid4(), fund_id=fund.id)
            db.add(row)
        row.full_name, row.designation, row.email, row.phone = t["full_name"], t.get("designation"), t.get("email"), t.get("phone")
        row.appointed_on = date.fromisoformat(t["appointed_on"]) if t.get("appointed_on") else None
        row.active, row.sort_order = True, order
        keep.add(row.id)
    for row in by_id.values():
        if row.id not in keep:
            row.active = False

    accounts = {a.id: a for a in fund.bank_accounts}
    keep = set()
    for order, a in enumerate(data["bank_accounts"]):
        row = accounts.get(_uuid(a["id"])) if a.get("id") else None
        if row is None:
            row = FundBankAccount(id=uuid.uuid4(), fund_id=fund.id)
            db.add(row)
        row.bank_id, row.branch_id = _uuid(a["bank_id"]), _uuid(a.get("branch_id"))
        row.account_name, row.account_number, row.currency = a["account_name"], a["account_number"], a["currency"]
        row.purpose = BankAccountPurpose(a["purpose"])
        row.active, row.sort_order = True, order
        keep.add(row.id)
    for row in accounts.values():
        if row.id not in keep:
            row.active = False


def _apply(db: Session, request: ApprovalRequest, checker: User) -> None:
    data = request.payload
    if data["action"] == "create":
        _check_code_free(db, data["code"], None, ignore_request=request.id)
        fund = Fund(**_fund_values(data))
        db.add(fund)
        db.flush()
        _sync_children(db, fund, data)
        # The maker and checker who set the fund up administer it from now on,
        # so its later changes can be made and approved without waiting on an admin.
        fund_access.grant(db, request.initiated_by_user_id, fund.id, checker.id)
        fund_access.grant(db, checker.id, fund.id, checker.id)
        request.entity_id = str(fund.id)
        request.fund_id = fund.id
        db.flush()
        db.refresh(fund)
        audit.record(db, checker.id, "fund", fund.id, "created", after=snapshot(fund), fund_id=fund.id)
        return

    fund = db.execute(select(Fund).where(Fund.id == _uuid(request.entity_id)).with_for_update()).scalar_one_or_none()
    if fund is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That fund no longer exists")
    before = snapshot(fund)
    values = _fund_values(data)
    frozen = [k for k in locked_fields(db, fund) if audit._jsonable(values[k]) != before[k]]
    if frozen:
        raise HTTPException(status.HTTP_409_CONFLICT, "Members have joined this fund since the change was requested, so its code and type can't change")
    if values["code"] != fund.code:
        _check_code_free(db, values["code"], fund.id, ignore_request=request.id)
    for field, value in values.items():
        setattr(fund, field, value)
    _sync_children(db, fund, data)
    db.flush()
    db.refresh(fund)
    audit.record(db, checker.id, "fund", fund.id, "updated", before=before, after=snapshot(fund), fund_id=fund.id)


approvals.register(approvals.ApprovalKind(
    name=KIND, label="Fund setup", checker_roles=frozenset({UserRole.scheme_config_checker}), apply=_apply,
))
