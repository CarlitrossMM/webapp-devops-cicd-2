"""Envía el reporte de resultados de CI (pytest/JUnit XML) a OpenObserve."""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests


def parse_junit_xml(xml_path: Path) -> dict[str, int]:
    """Extrae totales de pruebas desde el archivo JUnit XML generado por pytest."""
    if not xml_path.exists():
        return {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}

    tree = ET.parse(xml_path)
    root = tree.getroot()

    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    total = sum(int(s.attrib.get("tests", 0)) for s in suites)
    failures = sum(int(s.attrib.get("failures", 0)) for s in suites)
    errors = sum(int(s.attrib.get("errors", 0)) for s in suites)
    skipped = sum(int(s.attrib.get("skipped", 0)) for s in suites)
    passed = max(0, total - failures - errors - skipped)

    return {
        "total": total,
        "passed": passed,
        "failed": failures + errors,
        "errors": errors,
        "skipped": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reporta resultados de CI a OpenObserve")
    parser.add_argument("--xml", default="report.xml", help="Ruta al archivo JUnit XML")
    parser.add_argument(
        "--status",
        default=os.getenv("CI_JOB_STATUS", "unknown"),
        help="Estado del job (success / failure)",
    )
    args = parser.parse_args()

    stats = parse_junit_xml(Path(args.xml))
    payload = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline": os.getenv("GITHUB_WORKFLOW", "ci-cd"),
            "job_status": args.status,
            "commit_sha": os.getenv("GITHUB_SHA", "local"),
            "branch": os.getenv("GITHUB_REF_NAME", "main"),
            "actor": os.getenv("GITHUB_ACTOR", "local-dev"),
            "run_id": os.getenv("GITHUB_RUN_ID", "0"),
            "tests_total": stats["total"],
            "tests_passed": stats["passed"],
            "tests_failed": stats["failed"],
            "tests_skipped": stats["skipped"],
        }
    ]

    base_url = os.getenv("OPENOBSERVE_URL", "").rstrip("/")
    auth_header = os.getenv("OPENOBSERVE_AUTH_HEADER", "")

    print("Resumen CI:", json.dumps(payload[0], indent=2))

    if not base_url:
        print("OPENOBSERVE_URL no definido; omitiendo envío HTTP.")
        return 0

    target = f"{base_url}/api/default/cicd_pipelines/_json"
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        resp = requests.post(target, json=payload, headers=headers, timeout=10)
        print(f"OpenObserve respondió HTTP {resp.status_code}: {resp.text[:200]}")
    except requests.RequestException as exc:
        print(f"Advertencia: no se pudo enviar reporte a OpenObserve: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
