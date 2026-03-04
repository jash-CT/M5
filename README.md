# IoT & Industrial Control Stack

Production-ready stack for **device provisioning**, **telemetry ingestion**, **alerting and rules engines**, **fleet management**, and **legacy SCADA integration** (OPC-UA, Modbus).

## Architecture

```
                    +------------------+
                    |   MQTT Broker    |
                    |  (Mosquitto)     |
                    +--------+---------+
                             |
         +--------------------+--------------------+
         |                    |                    |
         v                    v                    v
+----------------+   +----------------+   +----------------+
| Ingest Service |   | Rules Engine   |   | SCADA Gateway   |
| (→ TimescaleDB)|   | (→ Alerts)    |   | (OPC-UA/Modbus)|
+----------------+   +----------------+   +----------------+
         |                    |                    |
         v                    v                    v
+----------------------------------------------------------------+
|                    PostgreSQL + TimescaleDB                     |
|  devices | fleets | telemetry (hypertable) | rules | alerts     |
+----------------------------------------------------------------+
         ^
         |
+----------------+
|   REST API     |  Provisioning, fleet, rules, alerts, telemetry
|   (FastAPI)    |
+----------------+
```

## Components

| Component | Role |
|-----------|------|
| **API** | REST API: device/fleet CRUD, provisioning tokens, rules, alerts, telemetry query |
| **Ingest** | Subscribes to MQTT `telemetry/#`, batches and writes to TimescaleDB |
| **Rules Engine** | Subscribes to MQTT telemetry, evaluates threshold (and expression) rules, creates alerts |
| **SCADA Gateway** | Polls OPC-UA and/or Modbus TCP, publishes to MQTT as telemetry |
| **PostgreSQL + TimescaleDB** | Device registry, fleets, telemetry time-series, rules, alerts |
| **Redis** | Cache / future pub-sub for alerting |
| **MQTT** | Device and gateway telemetry ingress |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) Python 3.12+ for local runs

### Run with Docker Compose

```bash
cp .env.example .env
# Edit .env if needed (passwords, OPCUA_ENDPOINT, MODBUS_HOST)
docker compose up -d
```

- **API**: http://localhost:8000 (docs: http://localhost:8000/docs)
- **Health**: http://localhost:8000/health
- **MQTT**: localhost:1883 (TCP), 9001 (WebSocket)

### Provision a device

1. Create a provisioning token (API or curl):

```bash
curl -X POST http://localhost:8000/api/v1/provisioning/tokens \
  -H "Content-Type: application/json" \
  -d '{"device_type": "sensor", "site_id": "plant-1", "expires_in_seconds": 3600}'
```

2. Claim the device (returns device ID and MQTT credentials):

```bash
curl -X POST http://localhost:8000/api/v1/provisioning/claim \
  -H "Content-Type: application/json" \
  -d '{"token": "<token>", "external_id": "sensor-001", "name": "Temperature 1", "device_type": "sensor"}'
```

3. Publish telemetry via MQTT (topic `telemetry/<device_id>/<metric>`, payload number or JSON with `value`, `ts`, `quality`).

### Telemetry formats (MQTT)

- **Single point**: Topic `telemetry/<device_id>/<metric>`, payload:
  - A number, or
  - JSON: `{"value": 22.5, "ts": "2025-03-04T12:00:00Z", "quality": 192}`
- **Batch**: Topic `telemetry/<device_id>`, payload:
  - `{"timestamp": "2025-03-04T12:00:00Z", "points": [{"metric": "temperature", "value": 22.5}, ...]}`

### Rules and alerts

- Create a rule (e.g. threshold) via `POST /api/v1/rules` with `condition_type: "threshold"`, `condition_config: {"metric": "temperature", "op": ">", "value": 80}`, and `scope_type` (device / fleet / global).
- When telemetry violates the condition, the rules engine creates an alert and updates the rule’s `last_triggered_at`.
- List/update alerts via `GET/PATCH /api/v1/alerts`.

### SCADA integration

- **OPC-UA**: Set `OPCUA_ENDPOINT=opc.tcp://your-server:4840` and optionally `OPCUA_NODE_MAP=metric_name:NodeId,...`. Gateway polls nodes and publishes to `telemetry/<SCADA_DEVICE_ID>/<metric>`.
- **Modbus TCP**: Set `MODBUS_HOST` and `MODBUS_PORT`. Gateway polls holding/input registers (default map in code; extend for your registers) and publishes to MQTT.
- Use `SCADA_DEVICE_ID` (default UUID) or map SCADA sources to platform devices via the `scada_sources` table.

## Configuration

| Variable | Description |
|----------|-------------|
| `POSTGRES_*` | PostgreSQL credentials and DB name |
| `REDIS_URL` | Redis connection URL |
| `MQTT_BROKER`, `MQTT_PORT` | MQTT broker for ingest, rules, gateway |
| `JWT_SECRET` | For future API auth |
| `OPCUA_ENDPOINT` | OPC-UA server URL (optional) |
| `MODBUS_HOST`, `MODBUS_PORT` | Modbus TCP (optional) |
| `SCADA_DEVICE_ID` | Virtual device ID for SCADA-originated telemetry |

## Project layout

```
├── config/           # Mosquitto config
├── scripts/          # DB init and schema (TimescaleDB)
├── shared/           # Shared Pydantic models and config
├── services/
│   ├── api/          # FastAPI app (provisioning, fleet, rules, alerts, telemetry)
│   ├── ingest/       # MQTT → TimescaleDB
│   ├── rules-engine/ # MQTT → rules → alerts
│   └── scada-gateway/# OPC-UA / Modbus → MQTT
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## License

MIT.
