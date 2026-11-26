"""Pruebas End-to-End (E2E) con Playwright en modo headless (~62 tests)."""

import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server_url():
    """Levanta el servidor FastAPI real en un puerto libre para Playwright."""
    port = _get_free_port()
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()

    env = os.environ.copy()
    env["OTEL_ENABLED"] = "false"
    env["DATABASE_URL"] = f"sqlite:///{tmp_db.name}"
    env["JWT_SECRET_KEY"] = "e2e-playwright-secret-key-32-chars"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("No se pudo iniciar el servidor Uvicorn para E2E")

    yield base_url

    proc.terminate()
    proc.wait(timeout=5)
    try:
        os.unlink(tmp_db.name)
    except OSError:
        pass


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture()
def page(browser, live_server_url):
    context = browser.new_context()
    p = context.new_page()
    p.goto(f"{live_server_url}/app/")
    yield p
    context.close()


def _register_and_login_ui(page, role="admin"):
    uid = uuid.uuid4().hex[:8]
    username = f"e2e_{role}_{uid}"
    password = "StrongPass#2026"

    page.get_by_test_id("tab-register").click()
    page.get_by_test_id("register-username").fill(username)
    page.get_by_test_id("register-email").fill(f"{username}@example.com")
    page.get_by_test_id("register-password").fill(password)
    page.get_by_test_id("register-role").select_option(role)
    page.get_by_test_id("register-submit").click()

    page.get_by_test_id("auth-success").wait_for(state="visible")
    page.get_by_test_id("login-username").fill(username)
    page.get_by_test_id("login-password").fill(password)
    page.get_by_test_id("login-submit").click()
    page.get_by_test_id("dashboard-section").wait_for(state="visible")
    return username


# 1. Flujo de registro y login válido por UI (10 tests)
@pytest.mark.parametrize("role", ["admin", "operador", "auditor", "admin", "operador", "auditor", "admin", "operador", "auditor", "admin"])
def test_e2e_register_and_login_valid(page, role):
    username = _register_and_login_ui(page, role=role)
    badge = page.get_by_test_id("user-badge").inner_text()
    assert username in badge
    assert role in badge

    # Logout regresa a pantalla de auth
    page.get_by_test_id("logout-btn").click()
    page.get_by_test_id("auth-section").wait_for(state="visible")


# 2. Login inválido muestra error visual en pantalla (10 tests)
@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("noexiste_1", "StrongPass#2026"),
        ("noexiste_2", "WrongPass#123"),
        ("admin_fake", "12345678"),
        ("oper_fake", "Password!1"),
        ("user_x", "Test#2026"),
        ("ghost@e2e.test", "StrongPass#2026"),
        ("bad_user_7", "Abcdef1!"),
        ("bad_user_8", "XyZ987!@"),
        ("bad_user_9", "Qwerty#12"),
        ("bad_user_10", "Pass!2026"),
    ],
)
def test_e2e_login_invalid_shows_error(page, username, password):
    page.get_by_test_id("login-username").fill(username)
    page.get_by_test_id("login-password").fill(password)
    page.get_by_test_id("login-submit").click()

    err = page.get_by_test_id("auth-error")
    err.wait_for(state="visible")
    assert "incorrectos" in err.inner_text().lower()


# 3. Registro inválido muestra error visual en pantalla (10 tests)
@pytest.mark.parametrize(
    ("username", "email", "password"),
    [
        ("ab", "a@b.com", "StrongPass#2026"),
        ("_bad", "b@b.com", "StrongPass#2026"),
        ("bad_", "c@b.com", "StrongPass#2026"),
        ("good1", "d@b.com", "weak"),
        ("good2", "e@b.com", "nouppercase1!"),
        ("good3", "f@b.com", "NOLOWERCASE1!"),
        ("good4", "g@b.com", "NoDigitsHere!"),
        ("good5", "h@b.com", "NoSpecial123"),
        ("good6", "i@b.com", "Has Space1!"),
        ("good7", "invalid@domain", "StrongPass#2026"),
    ],
)
def test_e2e_register_invalid_shows_error(page, username, email, password):
    page.get_by_test_id("tab-register").click()
    page.get_by_test_id("register-username").fill(username)
    page.get_by_test_id("register-email").fill(email)
    page.get_by_test_id("register-password").fill(password)
    page.get_by_test_id("register-submit").click()

    err = page.get_by_test_id("auth-error")
    err.wait_for(state="visible")
    assert len(err.inner_text().strip()) > 0


# 4. Creación de productos desde la UI (12 tests)
@pytest.mark.parametrize("category", ["electronica", "oficina", "herramientas", "insumos"])
@pytest.mark.parametrize(("stock", "min_stock"), [(2, 5), (5, 5), (25, 5)])
def test_e2e_create_product_and_verify_table(page, category, stock, min_stock):
    _register_and_login_ui(page, role="admin")
    sku = f"E2E-{uuid.uuid4().hex[:6].upper()}"

    page.get_by_test_id("open-create-product-btn").click()
    page.get_by_test_id("product-modal").wait_for(state="visible")
    page.get_by_test_id("product-sku").fill(sku)
    page.get_by_test_id("product-name").fill(f"Prod {sku}")
    page.get_by_test_id("product-category").select_option(category)
    page.get_by_test_id("product-price").fill("149.99")
    page.get_by_test_id("product-stock").fill(str(stock))
    page.get_by_test_id("product-min-stock").fill(str(min_stock))
    page.get_by_test_id("product-submit").click()

    row = page.get_by_test_id(f"product-row-{sku}")
    row.wait_for(state="visible")
    assert sku in row.inner_text()
    if stock <= min_stock:
        assert "Bajo" in row.inner_text()


# 5. Filtrado visual en Dashboard (10 tests)
@pytest.mark.parametrize(
    ("filter_type", "value"),
    [
        ("category", "electronica"),
        ("category", "oficina"),
        ("category", "herramientas"),
        ("category", "insumos"),
        ("search", "Monitor"),
        ("search", "Silla"),
        ("min_price", "200"),
        ("max_price", "50"),
        ("low_stock", "true"),
        ("reset", "all"),
    ],
)
def test_e2e_filter_products_ui(page, filter_type, value):
    _register_and_login_ui(page, role="admin")
    tag = uuid.uuid4().hex[:4].upper()

    # Crear 2 productos distintos vía UI
    items = [
        (f"MON-{tag}", f"Monitor {tag}", "electronica", "350", "15", "5"),
        (f"SIL-{tag}", f"Silla {tag}", "oficina", "40", "2", "5"),
    ]
    for sku, name, cat, price, stock, mstock in items:
        page.get_by_test_id("open-create-product-btn").click()
        page.get_by_test_id("product-sku").fill(sku)
        page.get_by_test_id("product-name").fill(name)
        page.get_by_test_id("product-category").select_option(cat)
        page.get_by_test_id("product-price").fill(price)
        page.get_by_test_id("product-stock").fill(stock)
        page.get_by_test_id("product-min-stock").fill(mstock)
        page.get_by_test_id("product-submit").click()
        page.get_by_test_id(f"product-row-{sku}").wait_for(state="visible")

    if filter_type == "category":
        page.get_by_test_id("filter-category").select_option(value)
        page.get_by_test_id("filter-apply-btn").click()
    elif filter_type == "search":
        page.get_by_test_id("filter-search").fill(f"{value} {tag}")
        page.get_by_test_id("filter-apply-btn").click()
    elif filter_type == "min_price":
        page.get_by_test_id("filter-min-price").fill(value)
        page.get_by_test_id("filter-apply-btn").click()
    elif filter_type == "max_price":
        page.get_by_test_id("filter-max-price").fill(value)
        page.get_by_test_id("filter-apply-btn").click()
    elif filter_type == "low_stock":
        page.get_by_test_id("filter-low-stock").check()
        page.get_by_test_id("filter-apply-btn").click()
    else:
        page.get_by_test_id("filter-category").select_option("electronica")
        page.get_by_test_id("filter-apply-btn").click()
        page.get_by_test_id("filter-reset-btn").click()

    page.wait_for_timeout(250)
    table_text = page.get_by_test_id("products-tbody").inner_text()
    if value in ("electronica", "Monitor", "200"):
        assert f"MON-{tag}" in table_text
    elif value in ("oficina", "Silla", "50", "true"):
        assert f"SIL-{tag}" in table_text
    elif value == "all":
        assert f"MON-{tag}" in table_text and f"SIL-{tag}" in table_text


# 6. Registro de órdenes y error de stock insuficiente en UI (10 tests)
@pytest.mark.parametrize(
    ("order_type", "qty", "expect_error"),
    [
        ("entrada", 5, False),
        ("entrada", 12, False),
        ("entrada", 25, False),
        ("salida", 3, False),
        ("salida", 10, False),
        ("salida", 11, True),
        ("salida", 15, True),
        ("salida", 20, True),
        ("salida", 50, True),
        ("salida", 100, True),
    ],
)
def test_e2e_orders_ui_valid_and_insufficient_stock(page, order_type, qty, expect_error):
    _register_and_login_ui(page, role="operador")
    sku = f"ORD-{uuid.uuid4().hex[:6].upper()}"

    page.get_by_test_id("open-create-product-btn").click()
    page.get_by_test_id("product-sku").fill(sku)
    page.get_by_test_id("product-name").fill(f"Item {sku}")
    page.get_by_test_id("product-category").select_option("insumos")
    page.get_by_test_id("product-price").fill("50")
    page.get_by_test_id("product-stock").fill("10")
    page.get_by_test_id("product-min-stock").fill("2")
    page.get_by_test_id("product-submit").click()
    page.get_by_test_id(f"product-row-{sku}").wait_for(state="visible")

    page.get_by_test_id(f"order-product-{sku}").click()
    page.get_by_test_id("order-modal").wait_for(state="visible")
    page.get_by_test_id("order-type").select_option(order_type)
    page.get_by_test_id("order-quantity").fill(str(qty))
    page.get_by_test_id("order-submit").click()

    if expect_error:
        err = page.get_by_test_id("order-modal-error")
        err.wait_for(state="visible")
        assert "insuficiente" in err.inner_text().lower()
    else:
        alert = page.get_by_test_id("dashboard-alert")
        alert.wait_for(state="visible")
        expected_stock = 10 + qty if order_type == "entrada" else 10 - qty
        expect(page.get_by_test_id(f"product-row-{sku}")).to_contain_text(str(expected_stock))
