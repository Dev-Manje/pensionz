---
name: pz-scheme-config
description: Use when adding or changing how funds, schemes/participating employers, benefit categories, portfolios, contribution rules, vesting scales, fee rules, insured-benefit rates, DB factor tables or regulatory parameters are configured in Pensionz. Covers the full backend→migration→schema→service→admin UI→seed chain.
---

# Fund, scheme and parameter configuration

Configuration is what lets one system run standalone, umbrella, personal and DB funds.
Behaviour is selected by **typed fields on the config row**, never by names
(`if fund.name == "OM Umbrella"` is forbidden).

## Configuration hierarchy (lower overrides higher, all effective-dated)

```
Regulatory parameters (system-wide: min contribution %, max lump sum %, retirement age band,
                      unemployment access wait, tax tables)
  └─ Fund (type, rules, trustees, bank accounts, portfolios offered, fee rules)
      └─ Scheme / participating employer (contribution day, billing, umbrella terms)
          └─ Benefit category (DC/DB design, rates, salary basis, NRA, vesting, default
             portfolio, insured benefits, choice allowed)
              └─ Member overrides (AVC %, portfolio choice) — only where the category allows
```

A category's rates may never go below the regulatory minimum in force on that date — validate
on save and on every change to the regulatory parameter.

## The chain — touch every layer, in this order

1. **Model** (`backend/app/models/<area>.py`) — new behaviour → extend a `str, enum.Enum`;
   new config → a `mapped_column`, nullable or server-defaulted. Rates that change over time
   go in **effective-dated rows** (`effective_from`, `effective_to`), not overwritten columns.
   Money `Numeric(18,2)`, rates/percentages `Numeric(9,6)`, unit prices `Numeric(18,6)`,
   units `Numeric(20,6)`, factors `Numeric(12,8)`.
2. **Alembic migration** — hand-written, short random hex id, `down_revision` = current head;
   enum values only added (`ALTER TYPE ... ADD VALUE IF NOT EXISTS`).
3. **Schemas** — `XCreate`, `XUpdate` (excludes fields frozen once members exist: fund type,
   DB/DC design, currency), `XOut`.
4. **API** — writes need `scheme_config_maker`; activation needs a different user with
   `scheme_config_checker` (maker-checker on config — a wrong rate misprices every member).
   Cross-field validation (employer % + employee % ≥ statutory; vesting scale monotonic;
   lump sum % ≤ regulatory max) returns `HTTPException(400, detail=...)`.
5. **Service behaviour** — resolve every parameter through one resolver
   (`services/config_resolver.py`: `resolve(member_or_category, key, as_of)`), so overrides and
   effective dates are applied the same way everywhere.
6. **Frontend types/API** — `frontend/src/api/types.ts`, `frontend/src/api/<area>.ts`.
7. **Admin UI** — `routes/admin/...`: show only fields relevant to the fund/category type,
   business-language helper text, a "changes take effect from" date, and a diff view for the
   checker before activation. Follow `pz-ui-conventions`.
8. **Downstream surfaces** — contribution schedule generation, benefit quotes, statements,
   member portal projections: check each understands the new setting.
9. **Seed** — `backend/app/seed.py`: one umbrella fund with two employers, one standalone DC,
   one DB fund, one personal pension fund, each with sample members.
10. **Docs** — update `docs/design/implementation-status.md`.

## Rules

- Never break existing members: new columns nullable/defaulted, enums only extended.
- Retire, don't delete (`status = closed_to_new_members` / `retired`).
- A config change never silently rewrites history: it applies from its effective date;
  recalculating past periods is an explicit, approved reprocessing job.
- Finish with `pz-verify` (migration applied, tsc clean, screenshot of the admin form and of a
  member/contribution affected by the new setting).
