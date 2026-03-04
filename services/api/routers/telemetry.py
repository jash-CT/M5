"""Telemetry query API (read-only; write is via MQTT ingest)."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.database import get_session

router = APIRouter()


class TelemetryRow(BaseModel):
    time: datetime
    device_id: UUID
    metric: str
    value: float | None
    value_int: int | None
    value_str: str | None
    quality: int | None


@router.get("/devices/{device_id}", response_model=list[dict])
async def get_device_telemetry(
    device_id: UUID,
    session: AsyncSession = Depends(get_session),
    metric: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(1000, ge=1, le=10000),
):
    q = """
        SELECT time, device_id, metric, value, value_int, value_str, quality
        FROM telemetry
        WHERE device_id = :device_id
    """
    params = {"device_id": str(device_id), "limit": limit}
    if metric:
        q += " AND metric = :metric"
        params["metric"] = metric
    if start:
        q += " AND time >= :start"
        params["start"] = start
    if end:
        q += " AND time <= :end"
        params["end"] = end
    q += " ORDER BY time DESC LIMIT :limit"
    r = await session.execute(text(q), params)
    rows = r.fetchall()
    return [
        {
            "time": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
            "device_id": str(row[1]),
            "metric": row[2],
            "value": row[3],
            "value_int": row[4],
            "value_str": row[5],
            "quality": row[6],
        }
        for row in rows
    ]


@router.get("/metrics/{metric}", response_model=list[dict])
async def get_metric_telemetry(
    metric: str,
    session: AsyncSession = Depends(get_session),
    device_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(1000, ge=1, le=10000),
):
    q = """
        SELECT time, device_id, metric, value, value_int, value_str, quality
        FROM telemetry
        WHERE metric = :metric
    """
    params = {"metric": metric, "limit": limit}
    if device_id:
        q += " AND device_id = :device_id"
        params["device_id"] = str(device_id)
    if start:
        q += " AND time >= :start"
        params["start"] = start
    if end:
        q += " AND time <= :end"
        params["end"] = end
    q += " ORDER BY time DESC LIMIT :limit"
    r = await session.execute(text(q), params)
    rows = r.fetchall()
    return [
        {
            "time": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
            "device_id": str(row[1]),
            "metric": row[2],
            "value": row[3],
            "value_int": row[4],
            "value_str": row[5],
            "quality": row[6],
        }
        for row in rows
    ]
