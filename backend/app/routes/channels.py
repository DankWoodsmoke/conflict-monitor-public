"""Channels registry endpoint — exposes channel metadata to the frontend."""

from copy import deepcopy

from fastapi import APIRouter, HTTPException

from app.seed_channels import get_all_channels

router = APIRouter(prefix="/channels", tags=["channels"])


def public_metadata(handle, meta):
    value = deepcopy(meta)
    value.update(
        handle=handle,
        metadata_status="inherited_unverified",
        reliability_basis="uncalibrated_legacy_editorial_prior",
        affiliation_status="unverified",
        metadata_origin_period="2026-03",
        bias_notes=f"Legacy March 2026 unverified note: {meta.get('bias_notes', '')}",
    )
    return value


@router.get("")
async def list_channels():
    """Expose inherited priors with their uncertainty; preserve registry values."""
    return [
        public_metadata(handle, meta) for handle, meta in get_all_channels().items()
    ]


@router.get("/{handle}")
async def get_channel(handle: str):
    """Return metadata for a specific channel handle."""
    registry = get_all_channels()
    canonical = next(
        (key for key in registry if key.casefold() == handle.casefold()), None
    )
    if canonical is None:
        raise HTTPException(status_code=404, detail="Channel not in registry")
    return public_metadata(canonical, registry[canonical])
