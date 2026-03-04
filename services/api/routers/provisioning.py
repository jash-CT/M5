"""Device provisioning: tokens and claim flow."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.database import get_session
from shared.models import DeviceProvisionRequest, DeviceProvisionResponse, ProvisioningTokenCreate, ProvisioningTokenResponse

router = APIRouter()


def _hash_token(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


@router.post("/tokens", response_model=ProvisioningTokenResponse, status_code=201)
async def create_provisioning_token(
    body: ProvisioningTokenCreate,
    session: AsyncSession = Depends(get_session),
):
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.expires_in_seconds)
    await session.execute(
        text("""
            INSERT INTO provisioning_tokens (token_hash, device_type, site_id, expires_at)
            VALUES (:token_hash, :device_type, :site_id, :expires_at)
        """),
        {
            "token_hash": token_hash,
            "device_type": body.device_type,
            "site_id": body.site_id,
            "expires_at": expires_at,
        },
    )
    await session.commit()
    return ProvisioningTokenResponse(token=raw, expires_at=expires_at)


@router.post("/claim", response_model=DeviceProvisionResponse, status_code=201)
async def claim_device(
    body: DeviceProvisionRequest,
    session: AsyncSession = Depends(get_session),
):
    token_hash = _hash_token(body.token)
    now = datetime.now(timezone.utc)
    r = await session.execute(
        text("""
            SELECT id, device_type, site_id FROM provisioning_tokens
            WHERE token_hash = :token_hash AND expires_at > :now AND used_at IS NULL
            FOR UPDATE
        """),
        {"token_hash": token_hash, "now": now},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    _tid, tok_device_type, site_id = row
    dtype = body.device_type or tok_device_type or "generic"
    # Create device and mark token used
    client_id = f"device_{body.external_id}"
    password = secrets.token_urlsafe(24)
    cred_hash = _hash_token(password)
    r2 = await session.execute(
        text("""
            INSERT INTO devices (external_id, name, device_type, site_id, status, credentials_hash)
            VALUES (:external_id, :name, :device_type, :site_id, 'active', :credentials_hash)
            RETURNING id
        """),
        {
            "external_id": body.external_id,
            "name": body.name,
            "device_type": dtype,
            "site_id": site_id,
            "credentials_hash": cred_hash,
        },
    )
    device_row = r2.fetchone()
    device_id = device_row[0]
    await session.execute(
        text("UPDATE provisioning_tokens SET used_at = :now WHERE id = :id"),
        {"now": now, "id": _tid},
    )
    await session.commit()
    return DeviceProvisionResponse(
        device_id=device_id,
        external_id=body.external_id,
        client_id=client_id,
        password=password,
        mqtt_telemetry_topic=f"telemetry/{device_id}/+",
    )
