-- IoT Platform Schema (PostgreSQL + TimescaleDB)

-- Device registry & provisioning
CREATE TABLE IF NOT EXISTS devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    device_type VARCHAR(100) NOT NULL,
    firmware_version VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',  -- pending, active, inactive, decommissioned
    site_id VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    credentials_hash VARCHAR(255),  -- hash of provisioned secret
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_devices_external_id ON devices(external_id);
CREATE INDEX idx_devices_status ON devices(status);
CREATE INDEX idx_devices_site_id ON devices(site_id);
CREATE INDEX idx_devices_device_type ON devices(device_type);

-- Fleet / group of devices
CREATE TABLE IF NOT EXISTS fleets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fleet_devices (
    fleet_id UUID NOT NULL REFERENCES fleets(id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fleet_id, device_id)
);

CREATE INDEX idx_fleet_devices_device ON fleet_devices(device_id);

-- Telemetry hypertable (TimescaleDB)
CREATE TABLE IF NOT EXISTS telemetry (
    time TIMESTAMPTZ NOT NULL,
    device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    metric VARCHAR(255) NOT NULL,
    value DOUBLE PRECISION,
    value_int BIGINT,
    value_str TEXT,
    value_json JSONB,
    quality INTEGER,  -- 0-192 quality code (OPC-UA style)
    PRIMARY KEY (time, device_id, metric)
);

SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_telemetry_device_time ON telemetry(device_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_metric_time ON telemetry(metric, time DESC);

-- Rules engine: rule definitions
CREATE TABLE IF NOT EXISTS rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    condition_type VARCHAR(32) NOT NULL,  -- threshold, expression, anomaly
    condition_config JSONB NOT NULL,     -- e.g. {"metric": "temperature", "op": ">", "value": 80}
    scope_type VARCHAR(32) NOT NULL,     -- device, fleet, global
    scope_id UUID,                       -- device_id or fleet_id
    severity VARCHAR(32) NOT NULL DEFAULT 'info',  -- info, warning, critical
    actions JSONB NOT NULL DEFAULT '[]', -- [{"type": "alert", "config": {...}}, {"type": "webhook", ...}]
    cooldown_seconds INTEGER DEFAULT 300,
    last_triggered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rules_enabled ON rules(enabled);
CREATE INDEX idx_rules_scope ON rules(scope_type, scope_id);

-- Alerts (fired by rules)
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES rules(id) ON DELETE CASCADE,
    device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT,
    severity VARCHAR(32) NOT NULL,
    payload JSONB DEFAULT '{}',
    status VARCHAR(32) NOT NULL DEFAULT 'open',  -- open, acknowledged, resolved
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(255),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_alerts_rule ON alerts(rule_id);
CREATE INDEX idx_alerts_device ON alerts(device_id);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_created ON alerts(created_at DESC);

-- SCADA bridge config (OPC-UA / Modbus sources mapped to internal devices)
CREATE TABLE IF NOT EXISTS scada_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    protocol VARCHAR(32) NOT NULL,  -- opcua, modbus
    config JSONB NOT NULL,         -- endpoint, security, node_ids / register map
    device_id UUID REFERENCES devices(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_scada_sources_device ON scada_sources(device_id);
CREATE INDEX idx_scada_sources_enabled ON scada_sources(enabled);

-- Provisioning tokens (one-time use)
CREATE TABLE IF NOT EXISTS provisioning_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    device_type VARCHAR(100),
    site_id VARCHAR(255),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_provisioning_tokens_expires ON provisioning_tokens(expires_at) WHERE used_at IS NULL;
