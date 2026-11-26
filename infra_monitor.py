"""Monitor de infraestructura con psutil y OpenTelemetry Metrics para OpenObserve."""

import logging
import os
import signal
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import psutil
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("infra_monitor")

THERMAL_PATH = Path("/sys/class/thermal/thermal_zone0/temp")
running = True


def _handle_signal(signum, frame):
    global running
    logger.info("Señal %s recibida, deteniendo monitor...", signum)
    running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def parse_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    if not raw:
        return headers
    for pair in raw.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            headers[k.strip()] = unquote(v.strip())
    return headers


def get_system_temperature(cpu_percent: float) -> tuple[float, str]:
    """Lee temperatura real del kernel o calcula temperatura simulada (38°C - 75°C)."""
    if THERMAL_PATH.exists():
        try:
            raw = THERMAL_PATH.read_text(encoding="utf-8").strip()
            celsius = round(float(raw) / 1000.0, 2)
            return celsius, "hardware_sensor"
        except (OSError, ValueError):
            pass

    clamped_cpu = max(0.0, min(100.0, cpu_percent))
    simulated = round(38.0 + (clamped_cpu / 100.0) * (75.0 - 38.0), 2)
    return simulated, "simulated_ec2"


def main() -> None:
    interval = int(os.getenv("INFRA_SCRAPE_INTERVAL", "10"))
    service_name = os.getenv("OTEL_SERVICE_NAME", "inventario-erp-infra")
    host_label = os.getenv("HOST_LABEL", os.uname().nodename if hasattr(os, "uname") else "ec2-host")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://host.docker.internal:5080/api/default").rstrip("/")
    headers = parse_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS", ""))

    resource = Resource.create({SERVICE_NAME: service_name, "host.name": host_label})
    exporter = OTLPMetricExporter(
        endpoint=f"{endpoint}/v1/metrics",
        headers=headers,
        timeout=5,
    )
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=interval * 1000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("infra_monitor", "1.0.0")
    cpu_gauge = meter.create_gauge("system_cpu_usage_percent", unit="%", description="Uso de CPU")
    ram_gauge = meter.create_gauge("system_memory_usage_percent", unit="%", description="Uso de RAM")
    net_sent_gauge = meter.create_gauge(
        "system_network_bytes_sent_per_sec", unit="By/s", description="Bytes enviados por segundo"
    )
    net_recv_gauge = meter.create_gauge(
        "system_network_bytes_recv_per_sec", unit="By/s", description="Bytes recibidos por segundo"
    )
    temp_gauge = meter.create_gauge(
        "system_temperature_celsius", unit="Cel", description="Temperatura del sistema"
    )

    # Inicializar lectura base de red y CPU
    psutil.cpu_percent(interval=None)
    prev_net = psutil.net_io_counters()
    prev_time = time.monotonic()

    logger.info("Monitor de infraestructura iniciado (intervalo=%ss, endpoint=%s)", interval, endpoint)

    while running:
        time.sleep(interval)
        if not running:
            break

        now = time.monotonic()
        elapsed = max(0.1, now - prev_time)

        cpu_pct = psutil.cpu_percent(interval=None)
        ram_pct = psutil.virtual_memory().percent

        curr_net = psutil.net_io_counters()
        bytes_sent_sec = round((curr_net.bytes_sent - prev_net.bytes_sent) / elapsed, 2)
        bytes_recv_sec = round((curr_net.bytes_recv - prev_net.bytes_recv) / elapsed, 2)
        prev_net = curr_net
        prev_time = now

        temp_c, temp_source = get_system_temperature(cpu_pct)
        common_attrs = {"host": host_label}

        cpu_gauge.set(cpu_pct, attributes=common_attrs)
        ram_gauge.set(ram_pct, attributes=common_attrs)
        net_sent_gauge.set(max(0.0, bytes_sent_sec), attributes=common_attrs)
        net_recv_gauge.set(max(0.0, bytes_recv_sec), attributes=common_attrs)
        temp_gauge.set(temp_c, attributes={**common_attrs, "source": temp_source})

        logger.info(
            "Métricas -> CPU=%.1f%% RAM=%.1f%% NetTx=%.1fB/s NetRx=%.1fB/s Temp=%.2f°C (%s)",
            cpu_pct,
            ram_pct,
            bytes_sent_sec,
            bytes_recv_sec,
            temp_c,
            temp_source,
        )

    provider.shutdown()
    sys.exit(0)


if __name__ == "__main__":
    main()
