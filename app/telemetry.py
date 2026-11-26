"""Configuración de Observabilidad Total con OpenTelemetry (Trazas, Métricas y Logs)."""

import json
import logging
from datetime import datetime, timezone
from urllib.parse import unquote

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings


def parse_otlp_headers(raw_headers: str) -> dict[str, str]:
    """Convierte OTEL_EXPORTER_OTLP_HEADERS (k=v,k2=v2) en diccionario."""
    headers: dict[str, str] = {}
    if not raw_headers:
        return headers
    for pair in raw_headers.split(","):
        if "=" in pair:
            key, val = pair.split("=", 1)
            headers[key.strip()] = unquote(val.strip())
    return headers


class StructuredJsonFormatter(logging.Formatter):
    """Formateador JSON estructurado con trace_id, span_id y excepciones."""

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        trace_id = format(ctx.trace_id, "032x") if ctx and ctx.is_valid else "0" * 32
        span_id = format(ctx.span_id, "016x") if ctx and ctx.is_valid else "0" * 16

        log_payload: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": settings.OTEL_SERVICE_NAME,
            "trace_id": trace_id,
            "span_id": span_id,
        }
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_payload.update(record.extra_fields)
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload, ensure_ascii=False)


class TelemetryMetrics:
    """Contenedor de instrumentos de métricas OpenTelemetry."""

    def __init__(self) -> None:
        meter = metrics.get_meter(settings.OTEL_SERVICE_NAME, settings.APP_VERSION)
        self.http_requests_total = meter.create_counter(
            name="http_requests_total",
            description="Total de peticiones HTTP recibidas",
            unit="1",
        )
        self.http_request_duration_ms = meter.create_histogram(
            name="http_request_duration_ms",
            description="Latencia de peticiones HTTP en milisegundos",
            unit="ms",
        )
        self.http_errors_total = meter.create_counter(
            name="http_errors_total",
            description="Conteo de errores HTTP 4xx y 5xx",
            unit="1",
        )


def setup_telemetry(app: FastAPI, engine) -> tuple[logging.Logger, TelemetryMetrics]:
    """Inicializa TracerProvider, MeterProvider, LoggerProvider e instrumentación."""
    logger = logging.getLogger("inventario_erp")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(StructuredJsonFormatter())
    logger.addHandler(stream_handler)

    if settings.OTEL_ENABLED:
        endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/")
        headers = parse_otlp_headers(settings.OTEL_EXPORTER_OTLP_HEADERS)
        resource = Resource.create(
            {
                SERVICE_NAME: settings.OTEL_SERVICE_NAME,
                SERVICE_VERSION: settings.APP_VERSION,
            }
        )

        # 1. Trazas
        tracer_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(
            endpoint=f"{endpoint}/v1/traces",
            headers=headers,
            timeout=5,
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)

        # 2. Métricas
        metric_exporter = OTLPMetricExporter(
            endpoint=f"{endpoint}/v1/metrics",
            headers=headers,
            timeout=5,
        )
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=15000
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        # 3. Logs
        logger_provider = LoggerProvider(resource=resource)
        log_exporter = OTLPLogExporter(
            endpoint=f"{endpoint}/v1/logs",
            headers=headers,
            timeout=5,
        )
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        set_logger_provider(logger_provider)
        otel_log_handler = LoggingHandler(
            level=logging.INFO, logger_provider=logger_provider
        )
        logger.addHandler(otel_log_handler)

        # Instrumentación automática FastAPI + SQLAlchemy
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(engine=engine)

    otel_metrics = TelemetryMetrics()
    return logger, otel_metrics
