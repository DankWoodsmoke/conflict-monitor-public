"""Authenticated selected-report local analysis; reads never start inference."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.security import require_admin_key
from app.services import local_briefing, report_analysis

router = APIRouter(prefix="/report-analysis", tags=["report analysis"],
                   dependencies=[Depends(require_admin_key)])


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_source_sha256: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")


@router.post("/{event_id}", status_code=202)
async def analyze(event_id: int, request: Request):
    try:
        return await report_analysis.enqueue(event_id, request.expected_source_sha256)
    except local_briefing.SourcePermissionRequired:
        raise HTTPException(403, {"code": "SourcePermissionRequired",
                                 "message": local_briefing.SOURCE_PERMISSION_MESSAGE}) from None
    except report_analysis.AnalysisDisabled:
        raise HTTPException(503, {"code": "AnalysisDisabled"}) from None
    except report_analysis.AnalysisBusy:
        raise HTTPException(409, {"code": "AnalysisBusy"}) from None
    except report_analysis.SourceChanged:
        raise HTTPException(409, {"code": "SourceChanged"}) from None
    except report_analysis.SourceUnavailable:
        raise HTTPException(422, {"code": "SourceUnavailable"}) from None
    except Exception:
        raise HTTPException(503, {"code": "AnalysisUnavailable"}) from None


@router.get("/jobs/{job_id}")
async def job(job_id: UUID):
    try:
        value = await report_analysis.get_job(str(job_id))
    except Exception:
        raise HTTPException(503, {"code": "AnalysisUnavailable"}) from None
    if value is None:
        raise HTTPException(404, {"code": "AnalysisExpiredOrUnknown"})
    return value
