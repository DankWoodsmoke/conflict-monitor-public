"""Operator-only bounded historical source scans, separate from public viewing."""
from uuid import UUID
from fastapi import APIRouter, Depends
from app.security import require_admin_key
from app.services import telegram_history as history

router = APIRouter(prefix="/history/backfill", tags=["historical collection"],
                   dependencies=[Depends(require_admin_key)])


@router.post("/jobs", status_code=201)
async def create_job(request: history.HistoryRequest):
    return await history.create_job(request)


@router.get("/jobs")
async def list_jobs():
    return await history.list_jobs()


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID):
    return await history.get_job(job_id)


@router.post("/jobs/{job_id}/run")
async def run_job(job_id: UUID):
    return await history.run_job(job_id)
