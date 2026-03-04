"""
SCADA gateway: bridge legacy SCADA (OPC-UA, Modbus) to platform telemetry via MQTT.
Reads from configured OPC-UA servers and/or Modbus devices and publishes to telemetry/<device_id>/<metric>.
"""
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from uuid import UUID

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
OPCUA_ENDPOINT = os.environ.get("OPCUA_ENDPOINT", "")
MODBUS_HOST = os.environ.get("MODBUS_HOST", "")
MODBUS_PORT = int(os.environ.get("MODBUS_PORT", "502"))
# Virtual device ID for SCADA sources (or use config per source)
SCADA_DEVICE_ID = os.environ.get("SCADA_DEVICE_ID", "00000000-0000-0000-0000-000000000001")

_mqtt_client: mqtt.Client | None = None


def get_mqtt():
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = mqtt.Client(client_id="scada-gateway")
        _mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        _mqtt_client.loop_start()
    return _mqtt_client


def publish_telemetry(device_id: str, metric: str, value: float | int | str, quality: int | None = None):
    client = get_mqtt()
    topic = f"telemetry/{device_id}/{metric}"
    payload = {"value": value, "ts": datetime.now(timezone.utc).isoformat()}
    if quality is not None:
        payload["quality"] = quality
    client.publish(topic, json.dumps(payload), qos=1)
    logger.debug("Published %s %s = %s", topic, metric, value)


# --- OPC-UA bridge (optional) ---
def run_opcua_bridge(endpoint: str, device_id: str, node_id_map: dict[str, str]):
    """Poll OPC-UA nodes and publish to MQTT. node_id_map: metric_name -> OPC-UA node id string."""
    try:
        from opcua import Client
    except ImportError:
        logger.warning("opcua not installed; OPC-UA bridge disabled")
        return
    client = Client(endpoint)
    try:
        client.connect()
        logger.info("OPC-UA connected to %s", endpoint)
    except Exception as e:
        logger.error("OPC-UA connection failed: %s", e)
        return
    while True:
        try:
            for metric, node_id in node_id_map.items():
                try:
                    node = client.get_node(node_id)
                    val = node.get_value()
                    if isinstance(val, (int, float, str)):
                        publish_telemetry(device_id, metric, val)
                    else:
                        publish_telemetry(device_id, metric, str(val))
                except Exception as e:
                    logger.debug("OPC-UA read %s: %s", metric, e)
            time.sleep(5)
        except Exception as e:
            logger.exception("OPC-UA poll error: %s", e)
            time.sleep(10)


# --- Modbus RTU/TCP bridge (optional) ---
def run_modbus_bridge(host: str, port: int, device_id: str, register_map: list[dict]):
    """
    Poll Modbus registers and publish to MQTT.
    register_map: [ {"metric": "temperature", "address": 0, "type": "holding"|"input", "scale": 0.1}, ... ]
    """
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        logger.warning("pymodbus not installed; Modbus bridge disabled")
        return
    client = ModbusTcpClient(host, port=port)
    try:
        client.connect()
        logger.info("Modbus TCP connected to %s:%s", host, port)
    except Exception as e:
        logger.error("Modbus connection failed: %s", e)
        return
    while True:
        try:
            for item in register_map:
                addr = item.get("address", 0)
                typ = item.get("type", "holding")
                metric = item.get("metric", f"reg_{addr}")
                scale = item.get("scale", 1.0)
                try:
                    if typ == "holding":
                        rr = client.read_holding_registers(addr, 1)
                    else:
                        rr = client.read_input_registers(addr, 1)
                    if rr.isError():
                        continue
                    val = rr.registers[0] * scale
                    publish_telemetry(device_id, metric, val)
                except Exception as e:
                    logger.debug("Modbus read %s: %s", metric, e)
            time.sleep(5)
        except Exception as e:
            logger.exception("Modbus poll error: %s", e)
            time.sleep(10)


def main():
    import threading
    threads = []
    if OPCUA_ENDPOINT:
        # Default node map: adjust via env or config file in production
        node_map = os.environ.get("OPCUA_NODE_MAP", "temperature:ns=2;i=2")
        node_id_map = {}
        for part in node_map.split(","):
            k, v = part.strip().split(":", 1)
            node_id_map[k.strip()] = v.strip()
        t = threading.Thread(target=run_opcua_bridge, args=(OPCUA_ENDPOINT, SCADA_DEVICE_ID, node_id_map), daemon=True)
        t.start()
        threads.append(t)
    if MODBUS_HOST:
        register_map = [
            {"metric": "temperature", "address": 0, "type": "holding", "scale": 0.1},
            {"metric": "pressure", "address": 1, "type": "holding", "scale": 0.01},
        ]
        t = threading.Thread(
            target=run_modbus_bridge,
            args=(MODBUS_HOST, MODBUS_PORT, SCADA_DEVICE_ID, register_map),
            daemon=True,
        )
        t.start()
        threads.append(t)
    if not threads:
        logger.info("No OPCUA_ENDPOINT or MODBUS_HOST set; gateway idle. Set env to enable bridges.")
        while True:
            time.sleep(60)
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
