"""Alerts CRUD and status updates."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.database import get_session
from shared.models import AlertResponse, AlertUpdate

router = APIRouter()


def _alert_from_row(row) -> AlertResponse:
    return AlertResponse(
        id=row[0],
        rule_id=row[1],
        device_id=row[2],
        title=row[3],
        message=row[4],
        severity=row[5],
        payload=row[6] or {},
        status=row[7],
        acknowledged_at=row[8],
        acknowledged_by=row[9],
        resolved_at=row[10],
        created_at=row[11],
    )


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    session: AsyncSession = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str | None = None,
    device_id: UUID | None = None,
    rule_id: UUID | None = None,
):
    q = """
        SELECT id, rule_id, device_id, title, message, severity, payload, status,
               acknowledged_at, acknowledged_by, resolved_at, created_at
        FROM alerts WHERE 1=1
    """
    params = {}
    if status:
        q += " AND status = :status"
        params["status"] = status
    if device_id:
        q += " AND device_id = :device_id"
        params["device_id"] = str(device_id)
    if rule_id:
        q += " AND rule_id = :rule_id"
        params["rule_id"] = str(rule_id)
    q += " ORDER BY created_at DESC OFFSET :skip LIMIT :limit"
    params["skip"] = skip
    params["limit"] = limit
    r = await session.execute(text(q), params)
    return [_alert_from_row(row) for row in r.fetchall()]


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        text("""
            SELECT id, rule_id, device_id, title, message, severity, payload, status,
                   acknowledged_at, acknowledged_by, resolved_at, created_at
            FROM alerts WHERE id = :id
        """),
        {"id": str(alert_id)},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _alert_from_row(row)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: UUID,
    body: AlertUpdate,
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    updates = ["status = :status"]
    params = {"id": str(alert_id), "status": body.status.value}
    if body.status.value == "acknowledged" and body.acknowledged_by:
        updates.append("acknowledged_at = :acknowledged_at")
        updates.append("acknowledged_by = :acknowledged_by")
        params["acknowledged_at"] = now
        params["acknowledged_by"] = body.acknowledged_by
    if body.status.value == "resolved":
        updates.append("resolved_at = :resolved_at")
        params["resolved_at"] = now
    q = f"""
        UPDATE alerts SET {", ".join(updates)}
        WHERE id = :id
        RETURNING id, rule_id, device_id, title, message, severity, payload, status,
                  acknowledged_at, acknowledged_by, resolved_at, created_at
    """
    r = await session.execute(text(q), params)
    row = r.fetchone()
    await session.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _alert_from_row(row)
