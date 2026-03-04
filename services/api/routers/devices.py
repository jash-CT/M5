"""Device CRUD and management."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.database import get_session
from shared.models import DeviceCreate, DeviceResponse, DeviceUpdate

router = APIRouter()


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    session: AsyncSession = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str | None = None,
    site_id: str | None = None,
    device_type: str | None = None,
):
    q = """
        SELECT id, external_id, name, device_type, firmware_version, status,
               site_id, metadata, last_seen_at, created_at, updated_at
        FROM devices
        WHERE 1=1
    """
    params = {}
    if status:
        q += " AND status = :status"
        params["status"] = status
    if site_id:
        q += " AND site_id = :site_id"
        params["site_id"] = site_id
    if device_type:
        q += " AND device_type = :device_type"
        params["device_type"] = device_type
    q += " ORDER BY created_at DESC OFFSET :skip LIMIT :limit"
    params["skip"] = skip
    params["limit"] = limit
    r = await session.execute(text(q), params)
    rows = r.fetchall()
    return [
        DeviceResponse(
            id=row[0],
            external_id=row[1],
            name=row[2],
            device_type=row[3],
            firmware_version=row[4],
            status=row[5],
            site_id=row[6],
            metadata=row[7] or {},
            last_seen_at=row[8],
            created_at=row[9],
            updated_at=row[10],
        )
        for row in rows
    ]


@router.post("", response_model=DeviceResponse, status_code=201)
async def create_device(
    body: DeviceCreate,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        text("""
            INSERT INTO devices (external_id, name, device_type, firmware_version, site_id, metadata, status)
            VALUES (:external_id, :name, :device_type, :firmware_version, :site_id, :metadata, 'pending')
            RETURNING id, external_id, name, device_type, firmware_version, status,
                      site_id, metadata, last_seen_at, created_at, updated_at
        """),
        {
            "external_id": body.external_id,
            "name": body.name,
            "device_type": body.device_type,
            "firmware_version": body.firmware_version,
            "site_id": body.site_id,
            "metadata": body.metadata,
        },
    )
    row = r.fetchone()
    await session.commit()
    return DeviceResponse(
        id=row[0],
        external_id=row[1],
        name=row[2],
        device_type=row[3],
        firmware_version=row[4],
        status=row[5],
        site_id=row[6],
        metadata=row[7] or {},
        last_seen_at=row[8],
        created_at=row[9],
        updated_at=row[10],
    )


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        text("""
            SELECT id, external_id, name, device_type, firmware_version, status,
                   site_id, metadata, last_seen_at, created_at, updated_at
            FROM devices WHERE id = :id
        """),
        {"id": str(device_id)},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceResponse(
        id=row[0],
        external_id=row[1],
        name=row[2],
        device_type=row[3],
        firmware_version=row[4],
        status=row[5],
        site_id=row[6],
        metadata=row[7] or {},
        last_seen_at=row[8],
        created_at=row[9],
        updated_at=row[10],
    )


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: UUID,
    body: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
):
    updates = []
    params = {"id": str(device_id)}
    if body.name is not None:
        updates.append("name = :name")
        params["name"] = body.name
    if body.device_type is not None:
        updates.append("device_type = :device_type")
        params["device_type"] = body.device_type
    if body.firmware_version is not None:
        updates.append("firmware_version = :firmware_version")
        params["firmware_version"] = body.firmware_version
    if body.status is not None:
        updates.append("status = :status")
        params["status"] = body.status.value
    if body.site_id is not None:
        updates.append("site_id = :site_id")
        params["site_id"] = body.site_id
    if body.metadata is not None:
        updates.append("metadata = :metadata")
        params["metadata"] = body.metadata
    if not updates:
        return await get_device(device_id, session)
    updates.append("updated_at = :updated_at")
    params["updated_at"] = datetime.utcnow()
    q = f"""
        UPDATE devices SET {", ".join(updates)}
        WHERE id = :id
        RETURNING id, external_id, name, device_type, firmware_version, status,
                  site_id, metadata, last_seen_at, created_at, updated_at
    """
    r = await session.execute(text(q), params)
    row = r.fetchone()
    await session.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceResponse(
        id=row[0], external_id=row[1], name=row[2], device_type=row[3],
        firmware_version=row[4], status=row[5], site_id=row[6], metadata=row[7] or {},
        last_seen_at=row[8], created_at=row[9], updated_at=row[10],
    )


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(text("DELETE FROM devices WHERE id = :id RETURNING id"), {"id": str(device_id)})
    await session.commit()
    if not r.fetchone():
        raise HTTPException(status_code=404, detail="Device not found")
