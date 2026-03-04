"""Fleet CRUD and device membership."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.database import get_session
from shared.models import FleetCreate, FleetDevicesUpdate, FleetResponse, FleetUpdate

router = APIRouter()


def _fleet_from_row(row) -> FleetResponse:
    return FleetResponse(
        id=row[0],
        name=row[1],
        description=row[2],
        metadata=row[3] or {},
        device_count=row[4] if len(row) > 4 else None,
        created_at=row[5] if len(row) > 5 else row[-2],
        updated_at=row[6] if len(row) > 6 else row[-1],
    )


@router.get("", response_model=list[FleetResponse])
async def list_fleets(
    session: AsyncSession = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    r = await session.execute(
        text("""
            SELECT f.id, f.name, f.description, f.metadata, f.created_at, f.updated_at,
                   (SELECT COUNT(*) FROM fleet_devices fd WHERE fd.fleet_id = f.id) AS device_count
            FROM fleets f
            ORDER BY f.created_at DESC
            OFFSET :skip LIMIT :limit
        """),
        {"skip": skip, "limit": limit},
    )
    rows = r.fetchall()
    return [
        FleetResponse(
            id=row[0],
            name=row[1],
            description=row[2],
            metadata=row[3] or {},
            device_count=row[4],
            created_at=row[5],
            updated_at=row[6],
        )
        for row in rows
    ]


@router.post("", response_model=FleetResponse, status_code=201)
async def create_fleet(
    body: FleetCreate,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        text("""
            INSERT INTO fleets (name, description, metadata)
            VALUES (:name, :description, :metadata)
            RETURNING id, name, description, metadata, created_at, updated_at
        """),
        {"name": body.name, "description": body.description, "metadata": body.metadata},
    )
    row = r.fetchone()
    await session.commit()
    return FleetResponse(
        id=row[0],
        name=row[1],
        description=row[2],
        metadata=row[3] or {},
        created_at=row[4],
        updated_at=row[5],
    )


@router.get("/{fleet_id}", response_model=FleetResponse)
async def get_fleet(
    fleet_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        text("""
            SELECT f.id, f.name, f.description, f.metadata, f.created_at, f.updated_at,
                   (SELECT COUNT(*) FROM fleet_devices fd WHERE fd.fleet_id = f.id)
            FROM fleets f WHERE f.id = :id
        """),
        {"id": str(fleet_id)},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Fleet not found")
    return FleetResponse(
        id=row[0],
        name=row[1],
        description=row[2],
        metadata=row[3] or {},
        device_count=row[4],
        created_at=row[5],
        updated_at=row[6],
    )


@router.patch("/{fleet_id}", response_model=FleetResponse)
async def update_fleet(
    fleet_id: UUID,
    body: FleetUpdate,
    session: AsyncSession = Depends(get_session),
):
    updates = []
    params = {"id": str(fleet_id)}
    if body.name is not None:
        updates.append("name = :name")
        params["name"] = body.name
    if body.description is not None:
        updates.append("description = :description")
        params["description"] = body.description
    if body.metadata is not None:
        updates.append("metadata = :metadata")
        params["metadata"] = body.metadata
    if not updates:
        return await get_fleet(fleet_id, session)
    updates.append("updated_at = :updated_at")
    params["updated_at"] = datetime.utcnow()
    q = f"""
        UPDATE fleets SET {", ".join(updates)}
        WHERE id = :id
        RETURNING id, name, description, metadata, created_at, updated_at
    """
    r = await session.execute(text(q), params)
    row = r.fetchone()
    await session.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Fleet not found")
    r2 = await session.execute(
        text("SELECT COUNT(*) FROM fleet_devices WHERE fleet_id = :id"),
        {"id": str(fleet_id)},
    )
    count = r2.scalar() or 0
    return FleetResponse(
        id=row[0], name=row[1], description=row[2], metadata=row[3] or {},
        device_count=count, created_at=row[4], updated_at=row[5],
    )


@router.delete("/{fleet_id}", status_code=204)
async def delete_fleet(
    fleet_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(text("DELETE FROM fleets WHERE id = :id RETURNING id"), {"id": str(fleet_id)})
    await session.commit()
    if not r.fetchone():
        raise HTTPException(status_code=404, detail="Fleet not found")


@router.get("/{fleet_id}/devices", response_model=list[UUID])
async def list_fleet_devices(
    fleet_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        text("SELECT device_id FROM fleet_devices WHERE fleet_id = :id"),
        {"id": str(fleet_id)},
    )
    return [row[0] for row in r.fetchall()]


@router.put("/{fleet_id}/devices")
async def set_fleet_devices(
    fleet_id: UUID,
    body: FleetDevicesUpdate,
    session: AsyncSession = Depends(get_session),
):
    await session.execute(text("DELETE FROM fleet_devices WHERE fleet_id = :id"), {"id": str(fleet_id)})
    for did in body.device_ids:
        await session.execute(
            text("INSERT INTO fleet_devices (fleet_id, device_id) VALUES (:fid, :did) ON CONFLICT DO NOTHING"),
            {"fid": str(fleet_id), "did": str(did)},
        )
    await session.commit()
    return {"updated": len(body.device_ids)}
