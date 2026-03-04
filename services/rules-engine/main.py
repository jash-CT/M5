"""
Rules engine: consume telemetry (from MQTT or Redis), evaluate rules, create alerts and run actions.
Subscribes to MQTT telemetry topics and evaluates threshold/expression rules per device.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from uuid import UUID

import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://iot:iot_secret@localhost:5432/iot_platform"
)
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
TELEMETRY_TOPIC = "telemetry/#"

# Cooldown cache: rule_id -> last_triggered_at
_cooldown: dict[str, float] = {}
_conn = None


def get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DATABASE_URL)
    return _conn


def try_device_id(s: str) -> UUID | None:
    try:
        return UUID(s)
    except Exception:
        return None


def get_rules_for_metric(metric: str, device_id: UUID, fleet_ids: list[UUID] | None) -> list[dict]:
    """Load rules that apply to this device/metric (threshold/expression, scope device/fleet/global)."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT id, name, condition_type, condition_config, scope_type, scope_id, severity, actions, cooldown_seconds, last_triggered_at
        FROM rules
        WHERE enabled = true
          AND (condition_config->>'metric' = %s OR condition_config->>'metric' IS NULL)
          AND (
            scope_type = 'global'
            OR (scope_type = 'device' AND scope_id = %s)
            OR (scope_type = 'fleet' AND scope_id = ANY(%s))
          )
        """,
        (metric, str(device_id), [str(x) for x in (fleet_ids or [])]),
    )
    rows = cur.fetchall()
    cur.close()
    return [dict(r) for r in rows]


def get_fleet_ids_for_device(device_id: UUID) -> list[UUID]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT fleet_id FROM fleet_devices WHERE device_id = %s", (str(device_id),))
    rows = cur.fetchall()
    cur.close()
    return [UUID(r[0]) for r in rows]


def evaluate_threshold(config: dict, value: float) -> bool:
    op = (config.get("op") or ">").strip()
    threshold = config.get("value")
    if threshold is None:
        return False
    try:
        t = float(threshold)
    except (TypeError, ValueError):
        return False
    if op == ">":
        return value > t
    if op == ">=":
        return value >= t
    if op == "<":
        return value < t
    if op == "<=":
        return value <= t
    if op == "==":
        return value == t
    if op == "!=":
        return value != t
    return False


def in_cooldown(rule_id: str, cooldown_seconds: int) -> bool:
    key = rule_id
    last = _cooldown.get(key, 0)
    return (time.time() - last) < cooldown_seconds


def run_actions(actions: list, alert_payload: dict):
    """Run rule actions: webhook, etc."""
    try:
        import urllib.request
        for a in actions or []:
            if a.get("type") == "webhook" and a.get("config", {}).get("url"):
                url = a["config"]["url"]
                data = json.dumps(alert_payload).encode()
                req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10)
                logger.info("Webhook sent: %s", url)
    except Exception as e:
        logger.warning("Action execution failed: %s", e)


def fire_alert(rule_id: str, device_id: UUID | None, title: str, message: str, severity: str, payload: dict, actions: list | None = None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        INSERT INTO alerts (rule_id, device_id, title, message, severity, payload, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'open')
        """,
        (rule_id, str(device_id) if device_id else None, title, message, severity, json.dumps(payload)),
    )
    conn.commit()
    cur.execute(
        "UPDATE rules SET last_triggered_at = %s WHERE id = %s",
        (datetime.now(timezone.utc), rule_id),
    )
    conn.commit()
    cur.close()
    run_actions(actions, {"title": title, "message": message, "severity": severity, "payload": payload})
    _cooldown[rule_id] = time.time()
    logger.info("Alert fired: rule=%s device=%s title=%s", rule_id, device_id, title)


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != "telemetry":
        return
    device_id = try_device_id(parts[1])
    metric = parts[2]
    if not device_id:
        return
    try:
        if payload.decode().lstrip("-").replace(".", "", 1).isdigit():
            value = float(payload)
        else:
            data = json.loads(payload)
            value = data.get("value")
        if value is None:
            return
        value = float(value)
    except (ValueError, TypeError, UnicodeDecodeError):
        return
    fleet_ids = get_fleet_ids_for_device(device_id)
    rules = get_rules_for_metric(metric, device_id, fleet_ids)
    for r in rules:
        if r["condition_type"] != "threshold":
            continue
        cfg = r["condition_config"] or {}
        if cfg.get("metric") and cfg.get("metric") != metric:
            continue
        if not evaluate_threshold(cfg, value):
            continue
        if in_cooldown(str(r["id"]), r["cooldown_seconds"] or 300):
            continue
        title = r.get("name") or f"Rule {r['id']}"
        message = f"Metric {metric} = {value} violated condition: {cfg}"
        fire_alert(
            str(r["id"]),
            device_id,
            title,
            message,
            r.get("severity") or "info",
            {"metric": metric, "value": value, "condition": cfg},
            r.get("actions"),
        )


def run():
    client = mqtt.Client(client_id="rules-engine")
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.subscribe(TELEMETRY_TOPIC, qos=1)
    logger.info("Rules engine connected to MQTT %s:%s", MQTT_BROKER, MQTT_PORT)
    client.loop_forever()


if __name__ == "__main__":
    run()
