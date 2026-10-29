import httpx
import pytest
from fastapi import Depends, FastAPI

from app import security


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [b"\xff", b"\xc3\xa9", b"wrong-key"])
async def test_malformed_or_wrong_admin_header_returns_forbidden_without_unhandled_type_error(monkeypatch, header):
    monkeypatch.setattr(security.settings, "admin_api_key", "fixture-private-admin")
    app = FastAPI()
    reached = []
    @app.post("/maintenance", dependencies=[Depends(security.require_admin_key)])
    async def maintenance():
        reached.append(True)
        return {"status": "unexpected"}
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://fixture") as client:
        response = await client.post("/maintenance", headers=[(b"x-admin-key", header)])
    assert response.status_code == 403
    assert "fixture-private-admin" not in response.text
    assert reached == []
