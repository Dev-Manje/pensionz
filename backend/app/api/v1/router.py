from fastapi import APIRouter

from app.api.v1 import approvals, auth, categories, fee_rules, funds, investment_options, kyc, ledger, member_imports, members, notifications, periods, receipts, reference, regulatory, schemes, setup, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(approvals.router)
api_router.include_router(notifications.router)
api_router.include_router(funds.router)
api_router.include_router(periods.router)
api_router.include_router(schemes.router)
api_router.include_router(regulatory.router)
api_router.include_router(investment_options.router)
api_router.include_router(categories.router)
api_router.include_router(setup.router)
api_router.include_router(fee_rules.router)
api_router.include_router(kyc.router)
api_router.include_router(reference.router)
# Before members: its /members/{member_id} would otherwise catch /members/imports.
api_router.include_router(member_imports.router)
api_router.include_router(members.router)
api_router.include_router(ledger.router)
api_router.include_router(receipts.router)
