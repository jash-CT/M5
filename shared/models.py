"""Shared Pydantic models for API and messaging."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


# --- Enums ---
class DeviceStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DECOMMISSIONED = "decommissioned"


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class RuleConditionType(str, Enum):
    THRESHOLD = "threshold"
    EXPRESSION = "expression"
    ANOMALY = "anomaly"


class RuleScopeType(str, Enum):
    DEVICE = "device"
    FLEET = "fleet"
    GLOBAL = "global"


# --- Device & Fleet ---
class DeviceCreate(BaseModel):
    external_id: str
    name: str
    device_type: str
    firmware_version: Optional[str] = None
    site_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    firmware_version: Optional[str] = None
    status: Optional[DeviceStatus] = None
    site_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DeviceResponse(BaseModel):
    id: UUID
    external_id: str
    name: str
    device_type: str
    firmware_version: Optional[str]
    status: str
    site_id: Optional[str]
    metadata: Dict[str, Any]
    last_seen_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class FleetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FleetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class FleetResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    metadata: Dict[str, Any]
    device_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class FleetDevicesUpdate(BaseModel):
    device_ids: List[UUID]


# --- Telemetry ---
class TelemetryPoint(BaseModel):
    metric: str
    value: Optional[float] = None
    value_int: Optional[int] = None
    value_str: Optional[str] = None
    value_json: Optional[Dict[str, Any]] = None
    quality: Optional[int] = None
    timestamp: Optional[datetime] = None


class TelemetryPayload(BaseModel):
    device_id: str
    timestamp: Optional[datetime] = None
    points: List[TelemetryPoint]


# --- Rules ---
class RuleConditionConfig(BaseModel):
    metric: Optional[str] = None
    op: Optional[str] = None  # >, <, >=, <=, ==, !=
    value: Optional[Union[float, int, str]] = None
    expression: Optional[str] = None  # for expression type


class RuleActionConfig(BaseModel):
    type: str  # alert, webhook, email, command
    config: Dict[str, Any] = Field(default_factory=dict)


class RuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True
    condition_type: RuleConditionType
    condition_config: Dict[str, Any]
    scope_type: RuleScopeType
    scope_id: Optional[UUID] = None
    severity: str = "info"
    actions: List[RuleActionConfig] = Field(default_factory=list)
    cooldown_seconds: int = 300


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    condition_type: Optional[RuleConditionType] = None
    condition_config: Optional[Dict[str, Any]] = None
    scope_type: Optional[RuleScopeType] = None
    scope_id: Optional[UUID] = None
    severity: Optional[str] = None
    actions: Optional[List[RuleActionConfig]] = None
    cooldown_seconds: Optional[int] = None


class RuleResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    enabled: bool
    condition_type: str
    condition_config: Dict[str, Any]
    scope_type: str
    scope_id: Optional[UUID]
    severity: str
    actions: List[Dict[str, Any]]
    cooldown_seconds: int
    last_triggered_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# --- Alerts ---
class AlertResponse(BaseModel):
    id: UUID
    rule_id: UUID
    device_id: Optional[UUID]
    title: str
    message: Optional[str]
    severity: str
    payload: Dict[str, Any]
    status: str
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime


class AlertUpdate(BaseModel):
    status: AlertStatus
    acknowledged_by: Optional[str] = None


# --- Provisioning ---
class ProvisioningTokenCreate(BaseModel):
    device_type: Optional[str] = None
    site_id: Optional[str] = None
    expires_in_seconds: int = 3600


class ProvisioningTokenResponse(BaseModel):
    token: str
    expires_at: datetime


class DeviceProvisionRequest(BaseModel):
    token: str
    external_id: str
    name: str
    device_type: Optional[str] = None


class DeviceProvisionResponse(BaseModel):
    device_id: UUID
    external_id: str
    client_id: str
    password: str
    mqtt_telemetry_topic: str
