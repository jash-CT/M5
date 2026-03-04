"""
Telemetry ingestion: subscribe to MQTT telemetry topics and write to TimescaleDB.
Topic patterns:
  - telemetry/<device_id>/<metric>  payload: number or JSON { "value": 1.0, "quality": 192, "ts": "..." }
  - telemetry/<device_id>          payload: JSON { "timestamp": "...", "points": [{ "metric": "...", "value": 1.0 }, ...] }
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import execute_values

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
TELEMETRY_TOPIC = "telemetry/#"

# In-memory batch for bulk insert
BATCH_SIZE = 100
BATCH_INTERVAL_SEC = 5
_batch: list[tuple] = []
_last_flush = 0.0
_conn = None


def get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DATABASE_URL)
    return _conn


def parse_ts(ts: str | float | None) -> datetime | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        if ts > 1e12:
            return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def flush_batch(force: bool = False):
    global _batch, _last_flush
    import time
    now = time.time()
    if not force and len(_batch) < BATCH_SIZE and (now - _last_flush) < BATCH_INTERVAL_SEC:
        return
    if not _batch:
        _last_flush = now
        return
    rows = _batch
    _batch = []
    _last_flush = now
    try:
        conn = get_conn()
        cur = conn.cursor()
        execute_values(
            cur,
            """
            INSERT INTO telemetry (time, device_id, metric, value, value_int, value_str, value_json, quality)
            VALUES %s
            ON CONFLICT (time, device_id, metric) DO UPDATE SET
                value = EXCLUDED.value,
                value_int = EXCLUDED.value_int,
                value_str = EXCLUDED.value_str,
                value_json = EXCLUDED.value_json,
                quality = EXCLUDED.quality
            """,
            rows,
            template="(%s::timestamptz, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s)",
        )
        conn.commit()
        cur.close()
        logger.debug("Flushed %d telemetry rows", len(rows))
    except Exception as e:
        logger.exception("Failed to flush telemetry: %s", e)
        _batch = rows + _batch  # re-queue


def try_device_id(s: str) -> UUID | None:
    try:
        return UUID(s)
    except Exception:
        return None


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload
    parts = topic.split("/")
    if len(parts) < 2 or parts[0] != "telemetry":
        return
    device_id_str = parts[1]
    device_id = try_device_id(device_id_str)
    if not device_id:
        logger.warning("Invalid device_id in topic: %s", topic)
        return
    now_utc = datetime.now(timezone.utc)
    # Single metric: telemetry/<device_id>/<metric>
    if len(parts) >= 3:
        metric = parts[2]
        try:
            if payload.isdigit() or (payload.decode().lstrip("-").replace(".", "", 1).isdigit()):
                value = float(payload)
                _batch.append((now_utc, str(device_id), metric, value, None, None, None, None))
            else:
                data = json.loads(payload)
                ts = parse_ts(data.get("ts") or data.get("timestamp"))
                t = ts or now_utc
                v = data.get("value")
                vi = data.get("value_int")
                vs = data.get("value_str")
                vj = data.get("value_json") or (data if isinstance(data, dict) and "value" not in data else None)
                q = data.get("quality")
                _batch.append((t, str(device_id), metric, v, vi, vs, json.dumps(vj) if vj else None, q))
        except (ValueError, TypeError) as e:
            value = None
            try:
                value = float(payload)
            except Exception:
                pass
            if value is not None:
                _batch.append((now_utc, str(device_id), metric, value, None, None, None, None))
            else:
                logger.warning("Unparseable payload on %s: %s", topic, e)
        flush_batch()
        return
    # Batch: telemetry/<device_id>
    try:
        data = json.loads(payload)
        ts = parse_ts(data.get("timestamp") or data.get("ts"))
        t = ts or now_utc
        points = data.get("points", [])
        for p in points:
            metric = p.get("metric") or "unknown"
            v = p.get("value")
            vi = p.get("value_int")
            vs = p.get("value_str")
            vj = p.get("value_json")
            q = p.get("quality")
            _batch.append((t, str(device_id), metric, v, vi, vs, json.dumps(vj) if vj else None, q))
        # Update last_seen on device
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE devices SET last_seen_at = %s WHERE id = %s",
                (t, str(device_id)),
            )
            conn.commit()
            cur.close()
        except Exception as ex:
            logger.debug("Update last_seen failed: %s", ex)
        flush_batch()
    except Exception as e:
        logger.warning("Batch telemetry parse error on %s: %s", topic, e)


def run():
    client = mqtt.Client(client_id="ingest-service")
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.subscribe(TELEMETRY_TOPIC, qos=1)
    logger.info("Ingest connected to MQTT %s:%s, subscribed to %s", MQTT_BROKER, MQTT_PORT, TELEMETRY_TOPIC)
    client.loop_start()
    import time
    try:
        while True:
            time.sleep(10)
            flush_batch(force=True)
    except KeyboardInterrupt:
        flush_batch(force=True)
        client.loop_stop()


if __name__ == "__main__":
    run()
