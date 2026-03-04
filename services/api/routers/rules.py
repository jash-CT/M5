"""Rules CRUD."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.database import get_session
from shared.models import RuleCreate, RuleResponse, RuleUpdate

router = APIRouter()


def _rule_from_row(row) -> RuleResponse:
    return RuleResponse(
        id=row[0],
        name=row[1],
        description=row[2],
        enabled=row[3],
        condition_type=row[4],
        condition_config=row[5] or {},
        scope_type=row[6],
        scope_id=row[7],
        severity=row[8],
        actions=row[9] or [],
        cooldown_seconds=row[10],
        last_triggered_at=row[11],
        created_at=row[12],
        updated_at=row[13],
    )


@router.get("", response_model=list[RuleResponse])
async def list_rules(
    session: AsyncSession = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    enabled: bool | None = None,
):
    q = """
        SELECT id, name, description, enabled, condition_type, condition_config,
               scope_type, scope_id, severity, actions, cooldown_seconds,
               last_triggered_at, created_at, updated_at
        FROM rules WHERE 1=1
    """
    params = {}
    if enabled is not None:
        q += " AND enabled = :enabled"
        params["enabled"] = enabled
    q += " ORDER BY created_at DESC OFFSET :skip LIMIT :limit"
    params["skip"] = skip
    params["limit"] = limit
    r = await session.execute(text(q), params)
    return [_rule_from_row(row) for row in r.fetchall()]


@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    body: RuleCreate,
    session: AsyncSession = Depends(get_session),
):
    actions_json = [a.model_dump() for a in body.actions]
    r = await session.execute(
        text("""
            INSERT INTO rules (name, description, enabled, condition_type, condition_config,
                              scope_type, scope_id, severity, actions, cooldown_seconds)
            VALUES (:name, :description, :enabled, :condition_type, :condition_config,
                    :scope_type, :scope_id, :severity, :actions, :cooldown_seconds)
            RETURNING id, name, description, enabled, condition_type, condition_config,
                      scope_type, scope_id, severity, actions, cooldown_seconds,
                      last_triggered_at, created_at, updated_at
        """),
        {
            "name": body.name,
            "description": body.description,
            "enabled": body.enabled,
            "condition_type": body.condition_type.value,
            "condition_config": body.condition_config,
            "scope_type": body.scope_type.value,
            "scope_id": str(body.scope_id) if body.scope_id else None,
            "severity": body.severity,
            "actions": actions_json,
            "cooldown_seconds": body.cooldown_seconds,
        },
    )
    row = r.fetchone()
    await session.commit()
    return _rule_from_row(row)


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        text("""
            SELECT id, name, description, enabled, condition_type, condition_config,
                   scope_type, scope_id, severity, actions, cooldown_seconds,
                   last_triggered_at, created_at, updated_at FROM rules WHERE id = :id
        """),
        {"id": str(rule_id)},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _rule_from_row(row)


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    body: RuleUpdate,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        text("""
            SELECT id, name, description, enabled, condition_type, condition_config,
                   scope_type, scope_id, severity, actions, cooldown_seconds,
                   last_triggered_at, created_at, updated_at FROM rules WHERE id = :id
        """),
        {"id": str(rule_id)},
    )
    row = r.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    updates = []
    params = {"id": str(rule_id), "updated_at": datetime.utcnow()}
    if body.name is not None:
        updates.append("name = :name")
        params["name"] = body.name
    if body.description is not None:
        updates.append("description = :description")
        params["description"] = body.description
    if body.enabled is not None:
        updates.append("enabled = :enabled")
        params["enabled"] = body.enabled
    if body.condition_type is not None:
        updates.append("condition_type = :condition_type")
        params["condition_type"] = body.condition_type.value
    if body.condition_config is not None:
        updates.append("condition_config = :condition_config")
        params["condition_config"] = body.condition_config
    if body.scope_type is not None:
        updates.append("scope_type = :scope_type")
        params["scope_type"] = body.scope_type.value
    if body.scope_id is not None:
        updates.append("scope_id = :scope_id")
        params["scope_id"] = str(body.scope_id)
    if body.severity is not None:
        updates.append("severity = :severity")
        params["severity"] = body.severity
    if body.actions is not None:
        updates.append("actions = :actions")
        params["actions"] = [a.model_dump() for a in body.actions]
    if body.cooldown_seconds is not None:
        updates.append("cooldown_seconds = :cooldown_seconds")
        params["cooldown_seconds"] = body.cooldown_seconds
    if not updates:
        return _rule_from_row(row)
    updates.append("updated_at = :updated_at")
    q = f"UPDATE rules SET {', '.join(updates)} WHERE id = :id RETURNING id, name, description, enabled, condition_type, condition_config, scope_type, scope_id, severity, actions, cooldown_seconds, last_triggered_at, created_at, updated_at"
    r2 = await session.execute(text(q), params)
    await session.commit()
    return _rule_from_row(r2.fetchone())


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(text("DELETE FROM rules WHERE id = :id RETURNING id"), {"id": str(rule_id)})
    await session.commit()
    if not r.fetchone():
        raise HTTPException(status_code=404, detail="Rule not found")
