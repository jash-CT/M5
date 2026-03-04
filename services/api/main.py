"""
IoT Platform API: device provisioning, fleet management, rules, alerts, telemetry query.
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.api.database import init_db
from services.api.routers import alerts, devices, fleets, provisioning, rules, telemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    # shutdown: close pools etc.
    from services.api.database import close_db
    await close_db()


app = FastAPI(
    title="IoT Platform API",
    description="Device provisioning, fleet management, telemetry, rules and alerting",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router, prefix="/api/v1/devices", tags=["devices"])
app.include_router(fleets.router, prefix="/api/v1/fleets", tags=["fleets"])
app.include_router(provisioning.router, prefix="/api/v1/provisioning", tags=["provisioning"])
app.include_router(rules.router, prefix="/api/v1/rules", tags=["rules"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
app.include_router(telemetry.router, prefix="/api/v1/telemetry", tags=["telemetry"])


@app.get("/health", tags=["health"])
async def health():
    from services.api.database import db_healthy
    from services.api.redis_client import redis_healthy
    db_ok = await db_healthy()
    redis_ok = await redis_healthy()
    status = "healthy" if (db_ok and redis_ok) else "unhealthy"
    return {
        "status": status,
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }


@app.get("/", tags=["root"])
async def root():
    return {"service": "IoT Platform API", "docs": "/docs"}
