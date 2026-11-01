"""Maker-checker for simple per-fund configuration records (FR-CFG-011).

Investment options, fee rules and similar records share one shape: a row
belonging to a fund, identified by a code unique within that fund, created
and changed only as a whole snapshot approved by a scheme-setup checker who
administers the fund. `FundConfig` captures that once; each record type
declares its model, fields and any extra validation.

Larger records with children or officers (funds, schemes) keep their own
services because their snapshots carry more than plain fields."""
import uuid
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.fund import Fund
from app.models.identity import User, UserRole
from app.services import approvals, audit


@dataclass
class FundConfig:
    kind: str
    label: str  # "Investment option"
    model: type
    fields: tuple[str, ...]  # includes "code"
    # field → converter from the JSON payload value back to the column type
    converters: dict[str, Callable[[Any], Any]] = field(default_factory=dict)
    # extra checks: (db, fund, values, existing row or None) → raise HTTPException
    validate: Callable[[Session, Fund, dict, Any], None] | None = None
    # extra lines for the checker (e.g. an employer's name for its id): (db, values) → dict
    readable: Callable[[Session, dict], dict] | None = None

    def __post_init__(self):
        approvals.register(approvals.ApprovalKind(
            name=self.kind, label=self.label, checker_roles=frozenset({UserRole.scheme_config_checker}), apply=self._apply,
        ))

    # ---- reading

    def snapshot(self, row) -> dict:
        return audit._jsonable({f: getattr(row, f) for f in self.fields})

    def pending_request_id(self, db: Session, row_id: uuid.UUID) -> uuid.UUID | None:
        return db.execute(
            select(ApprovalRequest.id).where(
                ApprovalRequest.kind == self.kind, ApprovalRequest.entity_id == str(row_id), ApprovalRequest.status == ApprovalStatus.pending,
            )
        ).scalar_one_or_none()

    def rows(self, db: Session, fund_id: uuid.UUID) -> list:
        return list(db.execute(select(self.model).where(self.model.fund_id == fund_id).order_by(self.model.code)).scalars())

    def get(self, db: Session, row_id: uuid.UUID, fund_id: uuid.UUID):
        row = db.get(self.model, row_id)
        if row is None or row.fund_id != fund_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{self.label} not found")
        return row

    # ---- proposing

    def _extra(self, db: Session, values: dict) -> dict:
        return audit._jsonable(self.readable(db, values)) if self.readable else {}

    def _values(self, data: dict) -> dict:
        values = {f: data.get(f) for f in self.fields}
        for f, convert in self.converters.items():
            if values.get(f) is not None:
                values[f] = convert(values[f])
        return values

    def _check_code_free(self, db: Session, fund_id: uuid.UUID, code: str, row_id: uuid.UUID | None, ignore_request: uuid.UUID | None = None) -> None:
        taken = db.execute(
            select(self.model.id).where(self.model.fund_id == fund_id, func.upper(self.model.code) == code.upper())
        ).scalar_one_or_none()
        if taken is not None and taken != row_id:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{self.label} code {code} is already used in this fund")
        waiting = db.execute(
            select(ApprovalRequest.id, ApprovalRequest.entity_id).where(
                ApprovalRequest.kind == self.kind, ApprovalRequest.status == ApprovalStatus.pending,
                ApprovalRequest.fund_id == fund_id, func.upper(ApprovalRequest.payload["code"].astext) == code.upper(),
            )
        ).all()
        for request_id, entity_id in waiting:
            same = row_id is not None and entity_id == str(row_id)
            if request_id != ignore_request and not same:
                raise HTTPException(status.HTTP_409_CONFLICT, f"{self.label} code {code} is already used by one waiting for approval")

    def propose_new(self, db: Session, maker: User, fund: Fund, data: dict) -> ApprovalRequest:
        values = self._values(audit._jsonable(data))
        if self.validate:
            self.validate(db, fund, values, None)
        self._check_code_free(db, fund.id, values["code"], None)
        request = approvals.submit(
            db, maker, self.kind, entity_type=self.model.__tablename__, entity_id=None,
            summary=f"New {self.label.lower()} {values['code']} — {data.get('name', '')} in fund {fund.code}",
            payload={"action": "create", "fund_id": str(fund.id), **audit._jsonable(data), **self._extra(db, values)},
            fund_id=fund.id,
        )
        db.commit()
        db.refresh(request)
        return request

    def propose_update(self, db: Session, maker: User, fund: Fund, row, data: dict) -> ApprovalRequest:
        proposed = audit._jsonable(data)
        current = self.snapshot(row)
        changed = [k for k in self.fields if proposed.get(k) != current.get(k)]
        if not changed:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing has changed")
        values = self._values(proposed)
        if self.validate:
            self.validate(db, fund, values, row)
        if "code" in changed:
            self._check_code_free(db, fund.id, values["code"], row.id)
        request = approvals.submit(
            db, maker, self.kind, entity_type=self.model.__tablename__, entity_id=row.id,
            summary=f"Change {self.label.lower()} {row.code} in fund {fund.code}: {', '.join(k.replace('_', ' ') for k in changed)}"[:300],
            payload={"action": "update", **proposed, **self._extra(db, values)},
            previous={**current, **self._extra(db, self._values(current))},
            fund_id=fund.id,
        )
        db.commit()
        db.refresh(request)
        return request

    # ---- applying

    def _apply(self, db: Session, request: ApprovalRequest, checker: User) -> None:
        data = request.payload
        values = self._values(data)
        fund = db.get(Fund, request.fund_id)
        if data["action"] == "create":
            if self.validate:
                self.validate(db, fund, values, None)
            self._check_code_free(db, fund.id, values["code"], None, ignore_request=request.id)
            row = self.model(fund_id=fund.id, **values)
            db.add(row)
            db.flush()
            request.entity_id = str(row.id)
            audit.record(db, checker.id, self.model.__tablename__, row.id, "created", after=self.snapshot(row), fund_id=fund.id)
            return
        row = db.execute(select(self.model).where(self.model.id == uuid.UUID(request.entity_id)).with_for_update()).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"That {self.label.lower()} no longer exists")
        before = self.snapshot(row)
        if self.validate:
            self.validate(db, fund, values, row)
        if values["code"] != row.code:
            self._check_code_free(db, fund.id, values["code"], row.id, ignore_request=request.id)
        for f, v in values.items():
            setattr(row, f, v)
        db.flush()
        audit.record(db, checker.id, self.model.__tablename__, row.id, "updated", before=before, after=self.snapshot(row), fund_id=fund.id)


def enum_of(cls: type[Enum]) -> Callable[[Any], Enum]:
    return lambda v: cls(v)


def as_date(v: Any) -> date:
    return v if isinstance(v, date) else date.fromisoformat(v)
