"""Pruebas parametrizadas de CRUD de productos, validaciones y filtros (~223 tests)."""

import pytest


# 1. Creación válida: 4 categorías x 4 precios x 3 configs de stock = 48 tests
@pytest.mark.parametrize("category", ["electronica", "oficina", "herramientas", "insumos"])
@pytest.mark.parametrize("price", [0.01, 19.99, 250.5, 99999.99])
@pytest.mark.parametrize(
    ("stock", "min_stock", "expected_low"),
    [(0, 5, True), (5, 5, True), (50, 10, False)],
)
def test_create_product_valid_matrix(
    client, users_and_tokens, category, price, stock, min_stock, expected_low
):
    headers = users_and_tokens["admin"]["headers"]
    sku = f"SKU-{category[:3].upper()}-{int(price * 100)}-{stock}"
    resp = client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": sku,
            "name": f"Item {sku}",
            "description": "Descripción de prueba",
            "category": category,
            "price": price,
            "stock": stock,
            "min_stock": min_stock,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sku"] == sku
    assert data["category"] == category
    assert data["price"] == price
    assert data["stock"] == stock
    assert data["low_stock"] is expected_low


# 2. SKUs inválidos (25 tests)
@pytest.mark.parametrize(
    "bad_sku",
    [
        "",
        "A",
        "AB",
        "A" * 33,
        "-ABC",
        "ABC-",
        "AB CD",
        "AB_CD",
        "AB.CD",
        "AB/CD",
        "AB@CD",
        "AB#CD",
        "AB$CD",
        "AB*CD",
        "   ",
        "---",
        "12",
        "A!",
        "SKU?01",
        "SKU+01",
        "SKU=01",
        "SKU,01",
        "SKU;01",
        "SKU:01",
        "ÑANDU-1",
    ],
)
def test_create_product_invalid_sku(client, users_and_tokens, bad_sku):
    headers = users_and_tokens["admin"]["headers"]
    resp = client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": bad_sku,
            "name": "Producto Inválido",
            "category": "electronica",
            "price": 10.0,
            "stock": 5,
            "min_stock": 1,
        },
    )
    assert resp.status_code == 422


# 3. Precios, stocks, nombres y categorías inválidos (30 tests)
@pytest.mark.parametrize(
    "override",
    [
        {"price": 0},
        {"price": -0.01},
        {"price": -100},
        {"price": 1_000_000.01},
        {"price": "no-num"},
        {"stock": -1},
        {"stock": -50},
        {"stock": 1_000_001},
        {"min_stock": -1},
        {"min_stock": -10},
        {"min_stock": 1_000_001},
        {"category": "ropa"},
        {"category": "alimentos"},
        {"category": ""},
        {"category": "ELECTRONICA"},
        {"name": ""},
        {"name": "A"},
        {"name": "   "},
        {"name": "X" * 121},
        {"description": "D" * 501},
        {"price": None},
        {"stock": None},
        {"category": None},
        {"sku": None},
        {"name": None},
        {"is_active": "maybe"},
        {"price": -1e5},
        {"stock": "abc"},
        {"min_stock": "xyz"},
        {"category": 123},
    ],
)
def test_create_product_invalid_fields(client, users_and_tokens, override):
    headers = users_and_tokens["admin"]["headers"]
    payload = {
        "sku": "VALID-001",
        "name": "Producto Válido",
        "category": "oficina",
        "price": 50.0,
        "stock": 10,
        "min_stock": 2,
    }
    payload.update(override)
    resp = client.post("/api/products", headers=headers, json=payload)
    assert resp.status_code == 422


# 4. Conflicto por SKU duplicado (10 tests)
@pytest.mark.parametrize(
    "dup_sku",
    [
        "DUP-100",
        "dup-100",
        " Dup-100 ",
        "DUP-100 ",
        " dup-100",
        "DuP-100",
        "dUp-100",
        "DUP-100  ",
        "  DUP-100",
        "dup-100  ",
    ],
)
def test_duplicate_sku_conflict(client, users_and_tokens, dup_sku):
    headers = users_and_tokens["admin"]["headers"]
    base = {
        "sku": "DUP-100",
        "name": "Original",
        "category": "insumos",
        "price": 12.5,
        "stock": 5,
        "min_stock": 1,
    }
    assert client.post("/api/products", headers=headers, json=base).status_code == 201
    second = {**base, "sku": dup_sku, "name": "Duplicado"}
    assert client.post("/api/products", headers=headers, json=second).status_code == 409


# 5. Actualización de productos (30 tests)
@pytest.mark.parametrize(
    ("patch", "expected_status"),
    [
        ({"name": "Nuevo Nombre"}, 200),
        ({"price": 199.99}, 200),
        ({"stock": 0}, 200),
        ({"stock": 100}, 200),
        ({"min_stock": 15}, 200),
        ({"category": "herramientas"}, 200),
        ({"category": "insumos"}, 200),
        ({"is_active": False}, 200),
        ({"is_active": True}, 200),
        ({"description": "Actualizada"}, 200),
        ({"sku": "UPD-NEW-1"}, 200),
        ({"sku": "upd-new-2"}, 200),
        ({"price": 1.0, "stock": 1, "min_stock": 1}, 200),
        ({"name": "Nombre Largo Válido", "is_active": False}, 200),
        ({"price": 0}, 422),
        ({"price": -10}, 422),
        ({"stock": -1}, 422),
        ({"min_stock": -5}, 422),
        ({"category": "invalida"}, 422),
        ({"sku": "X"}, 422),
        ({"sku": "-BAD"}, 422),
        ({"name": "A"}, 422),
        ({"name": "   "}, 422),
        ({"price": 1_000_001}, 422),
        ({"stock": 1_000_001}, 422),
        ({"sku": "OTHER-SKU"}, 409),
        ({"nonexistent": True}, 404),
        ({"price": -0.001}, 422),
        ({"min_stock": 1_000_001}, 422),
        ({"description": "Z" * 501}, 422),
    ],
)
def test_update_product_matrix(client, users_and_tokens, patch, expected_status):
    headers = users_and_tokens["admin"]["headers"]
    p1 = client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": "UPD-BASE",
            "name": "Base",
            "category": "electronica",
            "price": 100.0,
            "stock": 10,
            "min_stock": 5,
        },
    ).json()
    client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": "OTHER-SKU",
            "name": "Otro",
            "category": "oficina",
            "price": 20.0,
            "stock": 10,
            "min_stock": 2,
        },
    )

    target_id = 999999 if patch.get("nonexistent") else p1["id"]
    body = {k: v for k, v in patch.items() if k != "nonexistent"}
    resp = client.put(f"/api/products/{target_id}", headers=headers, json=body)
    assert resp.status_code == expected_status


# 6. Eliminación y consulta individual (15 tests)
@pytest.mark.parametrize("case_idx", range(15))
def test_delete_and_get_product_matrix(client, users_and_tokens, case_idx):
    admin_h = users_and_tokens["admin"]["headers"]
    oper_h = users_and_tokens["operador"]["headers"]
    aud_h = users_and_tokens["auditor"]["headers"]

    p = client.post(
        "/api/products",
        headers=admin_h,
        json={
            "sku": f"DEL-{case_idx:03d}",
            "name": f"Del Item {case_idx}",
            "category": "oficina",
            "price": 15.0 + case_idx,
            "stock": 10,
            "min_stock": 2,
        },
    ).json()

    if case_idx % 5 == 0:
        # Operador no puede eliminar
        assert client.delete(f"/api/products/{p['id']}", headers=oper_h).status_code == 403
    elif case_idx % 5 == 1:
        # Auditor no puede eliminar
        assert client.delete(f"/api/products/{p['id']}", headers=aud_h).status_code == 403
    elif case_idx % 5 == 2:
        # ID inexistente -> 404
        assert client.delete("/api/products/888888", headers=admin_h).status_code == 404
    elif case_idx % 5 == 3:
        # Con orden asociada -> 409
        client.post(
            "/api/orders",
            headers=admin_h,
            json={"product_id": p["id"], "order_type": "entrada", "quantity": 1},
        )
        assert client.delete(f"/api/products/{p['id']}", headers=admin_h).status_code == 409
    else:
        # Admin elimina OK y luego GET da 404
        assert client.delete(f"/api/products/{p['id']}", headers=admin_h).status_code == 200
        assert client.get(f"/api/products/{p['id']}", headers=admin_h).status_code == 404


# 7. Filtros de búsqueda (50 tests)
@pytest.mark.parametrize(
    ("params", "expected_skus"),
    [
        ({}, {"EL-1", "EL-2", "OF-1", "HE-1", "IN-1"}),
        ({"category": "electronica"}, {"EL-1", "EL-2"}),
        ({"category": "oficina"}, {"OF-1"}),
        ({"category": "herramientas"}, {"HE-1"}),
        ({"category": "insumos"}, {"IN-1"}),
        ({"category": "inexistente"}, set()),
        ({"min_price": 100}, {"EL-1", "EL-2", "HE-1"}),
        ({"min_price": 500}, {"EL-2"}),
        ({"min_price": 1000}, {"EL-2"}),
        ({"min_price": 2000}, set()),
        ({"max_price": 50}, {"OF-1", "IN-1"}),
        ({"max_price": 20}, {"IN-1"}),
        ({"max_price": 5}, set()),
        ({"min_price": 50, "max_price": 250}, {"EL-1", "HE-1"}),
        ({"min_price": 100, "max_price": 200}, {"EL-1", "HE-1"}),
        ({"min_price": 500, "max_price": 100}, set()),
        ({"search": "Laptop"}, {"EL-2"}),
        ({"search": "laptop"}, {"EL-2"}),
        ({"search": "EL-"}, {"EL-1", "EL-2"}),
        ({"search": "Taladro"}, {"HE-1"}),
        ({"search": "Papel"}, {"OF-1"}),
        ({"search": "Toner"}, {"IN-1"}),
        ({"search": "ergonómico"}, {"EL-1"}),
        ({"search": "no-existe-xyz"}, set()),
        ({"low_stock_only": True}, {"EL-2", "IN-1"}),
        ({"low_stock_only": False}, {"EL-1", "EL-2", "OF-1", "HE-1", "IN-1"}),
        ({"active_only": True}, {"EL-1", "EL-2", "OF-1", "IN-1"}),
        ({"active_only": False}, {"HE-1"}),
        ({"category": "electronica", "low_stock_only": True}, {"EL-2"}),
        ({"category": "electronica", "min_price": 300}, {"EL-2"}),
        ({"category": "electronica", "max_price": 300}, {"EL-1"}),
        ({"category": "oficina", "max_price": 50}, {"OF-1"}),
        ({"category": "oficina", "min_price": 50}, set()),
        ({"category": "herramientas", "active_only": True}, set()),
        ({"category": "herramientas", "active_only": False}, {"HE-1"}),
        ({"search": "EL", "active_only": True}, {"EL-1", "EL-2", "OF-1"}),
        ({"search": "EL-", "active_only": True}, {"EL-1", "EL-2"}),
        ({"search": "EL-1", "min_price": 100}, {"EL-1"}),
        ({"search": "EL-1", "min_price": 500}, set()),
        ({"low_stock_only": True, "active_only": True}, {"EL-2", "IN-1"}),
        ({"low_stock_only": True, "max_price": 30}, {"IN-1"}),
        ({"low_stock_only": True, "min_price": 500}, {"EL-2"}),
        ({"low_stock_only": True, "category": "oficina"}, set()),
        ({"min_price": 0, "max_price": 1500}, {"EL-1", "EL-2", "OF-1", "HE-1", "IN-1"}),
        ({"search": "Pro"}, {"EL-2", "HE-1"}),
        ({"search": "Pro", "category": "electronica"}, {"EL-2"}),
        ({"search": "Pro", "category": "herramientas"}, {"HE-1"}),
        ({"search": "Pro", "active_only": True}, {"EL-2"}),
        ({"search": "99999", "min_price": 1}, set()),
        ({"category": "insumos", "low_stock_only": True, "active_only": True}, {"IN-1"}),
    ],
)
def test_filter_products_matrix(client, users_and_tokens, params, expected_skus):
    headers = users_and_tokens["admin"]["headers"]
    seed = [
        {"sku": "EL-1", "name": "Mouse Ergonómico", "description": "Diseño ergonómico", "category": "electronica", "price": 120.0, "stock": 20, "min_stock": 5, "is_active": True},
        {"sku": "EL-2", "name": "Laptop Pro", "description": "Ultrabook", "category": "electronica", "price": 1200.0, "stock": 2, "min_stock": 5, "is_active": True},
        {"sku": "OF-1", "name": "Papel Carta", "description": "Resma 500 hojas", "category": "oficina", "price": 45.0, "stock": 30, "min_stock": 10, "is_active": True},
        {"sku": "HE-1", "name": "Taladro Pro", "description": "Percutor", "category": "herramientas", "price": 180.0, "stock": 15, "min_stock": 3, "is_active": False},
        {"sku": "IN-1", "name": "Toner Negro", "description": "Cartucho", "category": "insumos", "price": 18.0, "stock": 4, "min_stock": 4, "is_active": True},
    ]
    for item in seed:
        assert client.post("/api/products", headers=headers, json=item).status_code == 201

    resp = client.get("/api/products", headers=headers, params=params)
    assert resp.status_code == 200
    found_skus = {p["sku"] for p in resp.json()}
    assert found_skus == expected_skus


# 8. Alertas de stock bajo (15 tests)
@pytest.mark.parametrize(
    ("stock", "min_stock", "is_active", "should_alert"),
    [
        (0, 0, True, True),
        (0, 5, True, True),
        (5, 5, True, True),
        (4, 5, True, True),
        (6, 5, True, False),
        (100, 10, True, False),
        (0, 5, False, False),
        (3, 10, False, False),
        (10, 10, True, True),
        (11, 10, True, False),
        (1, 2, True, True),
        (2, 2, True, True),
        (3, 2, True, False),
        (1, 1, False, False),
        (50, 50, True, True),
    ],
)
def test_low_stock_alerts_matrix(client, users_and_tokens, stock, min_stock, is_active, should_alert):
    headers = users_and_tokens["admin"]["headers"]
    client.post(
        "/api/products",
        headers=headers,
        json={
            "sku": "ALERT-01",
            "name": "Alerta Test",
            "category": "insumos",
            "price": 10.0,
            "stock": stock,
            "min_stock": min_stock,
            "is_active": is_active,
        },
    )
    resp = client.get("/api/products/alerts/low-stock", headers=headers)
    assert resp.status_code == 200
    alerts = resp.json()
    assert (len(alerts) == 1) is should_alert
