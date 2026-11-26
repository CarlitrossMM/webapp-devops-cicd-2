"""Pruebas parametrizadas de lógica de órdenes, IVA, descuentos y consistencia (~160 tests)."""

import pytest

from app.routers.orders import calculate_discount_rate, calculate_order_totals


# 1. Reglas de descuento por volumen (30 tests)
@pytest.mark.parametrize(
    ("qty", "expected_rate"),
    [
        (1, 0.0),
        (2, 0.0),
        (5, 0.0),
        (8, 0.0),
        (9, 0.0),
        (10, 0.05),
        (11, 0.05),
        (15, 0.05),
        (18, 0.05),
        (19, 0.05),
        (20, 0.10),
        (21, 0.10),
        (25, 0.10),
        (30, 0.10),
        (40, 0.10),
        (48, 0.10),
        (49, 0.10),
        (50, 0.15),
        (51, 0.15),
        (60, 0.15),
        (75, 0.15),
        (100, 0.15),
        (150, 0.15),
        (200, 0.15),
        (500, 0.15),
        (1000, 0.15),
        (3, 0.0),
        (7, 0.0),
        (12, 0.05),
        (35, 0.10),
    ],
)
def test_discount_rate_tiers(qty, expected_rate):
    assert calculate_discount_rate(qty) == expected_rate


# 2. Cálculo de totales e IVA 16% (6 precios x 5 cantidades = 30 tests)
@pytest.mark.parametrize("unit_price", [1.0, 10.5, 99.99, 250.0, 500.25, 1234.56])
@pytest.mark.parametrize("qty", [1, 9, 10, 20, 50])
def test_calculate_order_totals_matrix(unit_price, qty):
    res = calculate_order_totals(unit_price, qty)
    expected_sub = round(unit_price * qty, 2)
    expected_disc = round(expected_sub * calculate_discount_rate(qty), 2)
    expected_taxable = round(expected_sub - expected_disc, 2)
    expected_tax = round(expected_taxable * 0.16, 2)
    expected_total = round(expected_taxable + expected_tax, 2)

    assert res["subtotal"] == expected_sub
    assert res["discount_amount"] == expected_disc
    assert res["tax_rate"] == 0.16
    assert res["tax_amount"] == expected_tax
    assert res["total"] == expected_total


# 3. Órdenes de entrada actualizan stock y totales (25 tests)
@pytest.mark.parametrize("initial_stock", [0, 5, 10, 25, 100])
@pytest.mark.parametrize("qty", [1, 10, 20, 50, 75])
def test_order_entrada_updates_stock_and_totals(client, users_and_tokens, initial_stock, qty):
    headers = users_and_tokens["operador"]["headers"]
    prod = client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": f"ENT-{initial_stock}-{qty}",
            "name": "Producto Entrada",
            "category": "insumos",
            "price": 100.0,
            "stock": initial_stock,
            "min_stock": 5,
        },
    ).json()

    resp = client.post(
        "/api/orders",
        headers=headers,
        json={"product_id": prod["id"], "order_type": "entrada", "quantity": qty, "notes": "Compra"},
    )
    assert resp.status_code == 201
    order = resp.json()
    assert order["order_type"] == "entrada"
    assert order["quantity"] == qty
    assert order["discount_rate"] == calculate_discount_rate(qty)

    updated = client.get(f"/api/products/{prod['id']}", headers=headers).json()
    assert updated["stock"] == initial_stock + qty


# 4. Órdenes de salida válidas (25 tests)
@pytest.mark.parametrize("initial_stock", [50, 60, 100, 120, 200])
@pytest.mark.parametrize("qty", [1, 5, 10, 25, 50])
def test_order_salida_valid_updates_stock(client, users_and_tokens, initial_stock, qty):
    headers = users_and_tokens["admin"]["headers"]
    prod = client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": f"SAL-{initial_stock}-{qty}",
            "name": "Producto Salida",
            "category": "electronica",
            "price": 80.0,
            "stock": initial_stock,
            "min_stock": 5,
        },
    ).json()

    resp = client.post(
        "/api/orders",
        headers=headers,
        json={"product_id": prod["id"], "order_type": "salida", "quantity": qty},
    )
    assert resp.status_code == 201
    updated = client.get(f"/api/products/{prod['id']}", headers=headers).json()
    assert updated["stock"] == initial_stock - qty


# 5. Rechazo por stock insuficiente y consistencia transaccional (20 tests)
@pytest.mark.parametrize(
    ("initial_stock", "requested_qty"),
    [
        (0, 1),
        (0, 10),
        (1, 2),
        (5, 6),
        (5, 10),
        (10, 11),
        (10, 50),
        (19, 20),
        (25, 26),
        (49, 50),
        (99, 100),
        (3, 100),
        (7, 8),
        (12, 15),
        (30, 31),
        (45, 90),
        (2, 3),
        (8, 9),
        (15, 16),
        (60, 61),
    ],
)
def test_order_salida_insufficient_stock_rejected_transactionally(
    client, users_and_tokens, initial_stock, requested_qty
):
    headers = users_and_tokens["admin"]["headers"]
    prod = client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": f"INSUF-{initial_stock}-{requested_qty}",
            "name": "Stock Insuficiente",
            "category": "herramientas",
            "price": 50.0,
            "stock": initial_stock,
            "min_stock": 2,
        },
    ).json()

    resp = client.post(
        "/api/orders",
        headers=headers,
        json={"product_id": prod["id"], "order_type": "salida", "quantity": requested_qty},
    )
    assert resp.status_code == 400

    # Consistencia: el stock no cambió y no se creó ninguna orden
    after_prod = client.get(f"/api/products/{prod['id']}", headers=headers).json()
    assert after_prod["stock"] == initial_stock
    orders = client.get("/api/orders", headers=headers, params={"product_id": prod["id"]}).json()
    assert len(orders) == 0


# 6. Payloads y estados inválidos en órdenes (20 tests)
@pytest.mark.parametrize(
    ("case_type", "payload_override", "expected_status"),
    [
        ("active", {"quantity": 0}, 422),
        ("active", {"quantity": -1}, 422),
        ("active", {"quantity": -50}, 422),
        ("active", {"quantity": 100_001}, 422),
        ("active", {"order_type": "ajuste"}, 422),
        ("active", {"order_type": ""}, 422),
        ("active", {"order_type": "ENTRADA"}, 422),
        ("active", {"product_id": 0}, 422),
        ("active", {"product_id": -5}, 422),
        ("active", {"notes": "N" * 256}, 422),
        ("active", {"quantity": "diez"}, 422),
        ("active", {"order_type": None}, 422),
        ("active", {"quantity": None}, 422),
        ("nonexistent", {}, 404),
        ("nonexistent", {"order_type": "salida"}, 404),
        ("inactive", {"order_type": "entrada"}, 400),
        ("inactive", {"order_type": "salida"}, 400),
        ("auditor", {"order_type": "entrada"}, 403),
        ("auditor", {"order_type": "salida"}, 403),
        ("active", {"notes": "Nota válida"}, 201),
    ],
)
def test_order_invalid_payloads_and_states(
    client, users_and_tokens, case_type, payload_override, expected_status
):
    admin_h = users_and_tokens["admin"]["headers"]
    req_h = users_and_tokens["auditor"]["headers"] if case_type == "auditor" else admin_h

    prod = client.post(
        "/api/products",
        headers=admin_h,
        json={
            "sku": "ORD-STATE-1",
            "name": "Producto Estado",
            "category": "oficina",
            "price": 30.0,
            "stock": 20,
            "min_stock": 2,
            "is_active": case_type != "inactive",
        },
    ).json()

    pid = 999999 if case_type == "nonexistent" else prod["id"]
    payload = {"product_id": pid, "order_type": "entrada", "quantity": 2}
    payload.update(payload_override)

    resp = client.post("/api/orders", headers=req_h, json=payload)
    assert resp.status_code == expected_status


# 7. Filtros de listado de órdenes (10 tests)
@pytest.mark.parametrize(
    ("filter_params", "expected_count"),
    [
        ({}, 4),
        ({"order_type": "entrada"}, 2),
        ({"order_type": "salida"}, 2),
        ({"order_type": "invalido"}, 0),
        ({"product_id": 1}, 2),
        ({"product_id": 2}, 2),
        ({"product_id": 9999}, 0),
        ({"order_type": "entrada", "product_id": 1}, 1),
        ({"order_type": "salida", "product_id": 1}, 1),
        ({"order_type": "salida", "product_id": 2}, 1),
    ],
)
def test_list_orders_filtering(client, users_and_tokens, filter_params, expected_count):
    headers = users_and_tokens["admin"]["headers"]
    p1 = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "FLT-1", "name": "P1", "category": "oficina", "price": 10.0, "stock": 20, "min_stock": 2},
    ).json()
    p2 = client.post(
        "/api/products",
        headers=headers,
        json={"sku": "FLT-2", "name": "P2", "category": "insumos", "price": 20.0, "stock": 20, "min_stock": 2},
    ).json()

    for pid in (p1["id"], p2["id"]):
        client.post("/api/orders", headers=headers, json={"product_id": pid, "order_type": "entrada", "quantity": 5})
        client.post("/api/orders", headers=headers, json={"product_id": pid, "order_type": "salida", "quantity": 2})

    # Mapear product_id lógico 1/2 a los IDs reales
    params = dict(filter_params)
    if params.get("product_id") == 1:
        params["product_id"] = p1["id"]
    elif params.get("product_id") == 2:
        params["product_id"] = p2["id"]

    resp = client.get("/api/orders", headers=headers, params=params)
    assert resp.status_code == 200
    assert len(resp.json()) == expected_count
