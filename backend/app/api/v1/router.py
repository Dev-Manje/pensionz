from fastapi import APIRouter

from app.api.v1 import approvals, auth, funds, notifications, reference, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(approvals.router)
api_router.include_router(notifications.router)
api_router.include_router(funds.router)
api_router.include_router(reference.router)
