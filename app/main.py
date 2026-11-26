"""Punto de entrada de FastAPI, middleware de observabilidad y archivos estáticos."""

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, init_db
from app.routers import auth, orders, products
from app.telemetry import setup_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar la aplicación."""
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Sistema de Gestión de Inventario y Órdenes (Mini-ERP) con OpenTelemetry",
    lifespan=lifespan,
)

logger, otel_metrics = setup_telemetry(app, engine)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Registra latencia, conteo de peticiones, errores 4xx/5xx y logs JSON."""
    start = time.perf_counter()
    path = request.url.path
    method = request.method
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        logger.exception(
            "Excepción no controlada en petición HTTP",
            extra={
                "extra_fields": {
                    "http_method": method,
                    "http_path": path,
                    "statusCode": 500,
                    "error": str(exc),
                }
            },
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"},
        )
    finally:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
        attrs = {
            "method": method,
            "endpoint": path,
            "statusCode": status_code,
        }
        otel_metrics.http_requests_total.add(1, attributes=attrs)
        otel_metrics.http_request_duration_ms.record(elapsed_ms, attributes=attrs)

        if status_code >= 400:
            otel_metrics.http_errors_total.add(
                1,
                attributes={
                    "method": method,
                    "endpoint": path,
                    "statusCode": status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.warning(
                f"HTTP {status_code} en {method} {path}",
                extra={
                    "extra_fields": {
                        "http_method": method,
                        "http_path": path,
                        "statusCode": status_code,
                        "latency_ms": elapsed_ms,
                    }
                },
            )
        else:
            logger.info(
                f"HTTP {status_code} en {method} {path}",
                extra={
                    "extra_fields": {
                        "http_method": method,
                        "http_path": path,
                        "statusCode": status_code,
                        "latency_ms": elapsed_ms,
                    }
                },
            )


app.include_router(auth.router)
app.include_router(products.router)
app.include_router(orders.router)


@app.get("/health", tags=["Sistema"])
def healthcheck() -> dict[str, str]:
    """Endpoint de salud para Docker y CI/CD."""
    return {
        "status": "ok",
        "service": settings.OTEL_SERVICE_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/api/debug/error", tags=["Sistema"])
def simulate_internal_error():
    """Endpoint controlado para pruebas de alertas 500 en OpenObserve."""
    raise RuntimeError("Error 500 simulado para pruebas de observabilidad")


static_dir = Path(__file__).resolve().parent / "static"
app.mount("/app", StaticFiles(directory=str(static_dir), html=True), name="frontend")


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirige la raíz a la interfaz web."""
    return RedirectResponse(url="/app/")
