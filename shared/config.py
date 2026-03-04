"""Shared configuration loading from environment."""
import os
from typing import Optional


def get_env(key: str, default: Optional[str] = None) -> str:
    v = os.environ.get(key, default)
    if v is None:
        raise RuntimeError(f"Missing required env: {key}")
    return v


def get_env_int(key: str, default: int = 0) -> int:
    return int(os.environ.get(key, str(default)))


def get_env_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


class DatabaseConfig:
    def __init__(self) -> None:
        self.url: str = get_env("DATABASE_URL", "postgresql://iot:iot_secret@localhost:5432/iot_platform")

    @property
    def sync_url(self) -> str:
        return self.url


class RedisConfig:
    def __init__(self) -> None:
        self.url: str = get_env("REDIS_URL", "redis://localhost:6379/0")


class MQTTConfig:
    def __init__(self) -> None:
        self.broker: str = get_env("MQTT_BROKER", "localhost")
        self.port: int = get_env_int("MQTT_PORT", 1883)
        self.telemetry_topic: str = "telemetry/+/+"
        self.telemetry_topic_prefix: str = "telemetry/"


class Settings:
    def __init__(self) -> None:
        self.database = DatabaseConfig()
        self.redis = RedisConfig()
        self.mqtt = MQTTConfig()
