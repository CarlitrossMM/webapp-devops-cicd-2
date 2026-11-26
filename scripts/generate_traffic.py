"""Generador de tráfico normal y errores 404/500 para poblar gráficas en OpenObserve."""

import argparse
import random
import time
import uuid

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Simula tráfico hacia Inventario ERP")
    parser.add_argument("--url", default="http://localhost:8000", help="URL base del servidor")
    parser.add_argument("--requests", type=int, default=60, help="Cantidad de ciclos a ejecutar")
    parser.add_argument("--delay", type=float, default=0.2, help="Pausa entre peticiones (seg)")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    username = f"traffic_{uuid.uuid4().hex[:8]}"
    password = "TrafficUser#2026"

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        # 1. Registro y login
        client.post(
            "/api/auth/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": password,
                "role": "admin",
            },
        )
        login_resp = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        login_resp.raise_for_status()
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Crear productos semilla
        product_ids = []
        categories = ["electronica", "oficina", "herramientas", "insumos"]
        for idx in range(5):
            sku = f"TRF-{uuid.uuid4().hex[:6].upper()}"
            resp = client.post(
                "/api/products",
                headers=headers,
                json={
                    "sku": sku,
                    "name": f"Producto Tráfico {idx + 1}",
                    "category": random.choice(categories),
                    "price": round(random.uniform(15.0, 450.0), 2),
                    "stock": random.randint(20, 100),
                    "min_stock": 10,
                },
            )
            if resp.status_code == 201:
                product_ids.append(resp.json()["id"])

        # 3. Ciclo de tráfico mixto (2xx, 400, 401, 404, 500)
        stats = {"2xx": 0, "4xx": 0, "5xx": 0}
        for i in range(args.requests):
            roll = random.random()
            if roll < 0.65:
                # Tráfico normal: listar, filtrar, consultar alertas y registrar orden
                r = client.get("/api/products", headers=headers, params={"category": random.choice(categories)})
                if product_ids and i % 3 == 0:
                    client.post(
                        "/api/orders",
                        headers=headers,
                        json={
                            "product_id": random.choice(product_ids),
                            "order_type": random.choice(["entrada", "salida"]),
                            "quantity": random.randint(1, 5),
                            "notes": "Simulación automática",
                        },
                    )
            elif roll < 0.80:
                # Error 404
                r = client.get(f"/api/products/{random.randint(99999, 999999)}", headers=headers)
            elif roll < 0.90:
                # Error 401 / 422
                if random.random() < 0.5:
                    r = client.get("/api/products", headers={"Authorization": "Bearer token-invalido"})
                else:
                    r = client.post("/api/products", headers=headers, json={"sku": "X", "price": -10})
            else:
                # Error 500 controlado
                r = client.get("/api/debug/error")

            if r.status_code < 400:
                stats["2xx"] += 1
            elif r.status_code < 500:
                stats["4xx"] += 1
            else:
                stats["5xx"] += 1

            time.sleep(args.delay)

        print(f"Simulación completada en {base_url}: {stats}")


if __name__ == "__main__":
    main()
