"""Pruebas parametrizadas de autenticación, validación, JWT y RBAC (~190 tests)."""

from datetime import timedelta

import jwt
import pytest

from app.auth import create_access_token, hash_password
from app.config import settings
from app.models import User


# 1. Registro válido (5 x 3 x 2 = 30 tests)
@pytest.mark.parametrize("username", ["alice01", "bob_erp", "carlos-99", "devUser1", "qa_ops_2"])
@pytest.mark.parametrize("role", ["admin", "operador", "auditor"])
@pytest.mark.parametrize("password", ["Secure#2026", "Valid!Pass99"])
def test_valid_registration_matrix(client, username, role, password):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@empresa.com",
            "password": password,
            "role": role,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == username
    assert data["email"] == f"{username.lower()}@empresa.com"
    assert data["role"] == role
    assert data["is_active"] is True
    assert "hashed_password" not in data


# 2. Emails inválidos (25 tests)
@pytest.mark.parametrize(
    "bad_email",
    [
        "",
        "plainaddress",
        "@no-local.com",
        "user@",
        "user@.com",
        "user@domain",
        "user@domain..com",
        "user name@domain.com",
        "user@dom ain.com",
        "user@@domain.com",
        ".user@domain.com",
        "user.@domain.com",
        "user@domain.",
        "user@-domain.com",
        "user@domain-.com",
        "user@123",
        "<>@domain.com",
        "user@domain,com",
        "user@domain;com",
        "user\n@domain.com",
        "user\t@domain.com",
        "user@.invalid",
        "test@.org",
        "test@sub..example.com",
        "not-an-email-at-all",
    ],
)
def test_invalid_emails(client, bad_email):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "validuser1",
            "email": bad_email,
            "password": "StrongPass#2026",
            "role": "operador",
        },
    )
    assert resp.status_code == 422


# 3. Usernames inválidos (20 tests)
@pytest.mark.parametrize(
    "bad_username",
    [
        "",
        "a",
        "ab",
        "a" * 31,
        "_leading",
        "-leading",
        "trailing_",
        "trailing-",
        "user name",
        "user.name",
        "user@name",
        "user$name",
        "user!name",
        "user/name",
        "user\\name",
        "áéíóú",
        "   ",
        "--",
        "__",
        "user*123",
    ],
)
def test_invalid_usernames(client, bad_username):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": bad_username,
            "email": "valid@empresa.com",
            "password": "StrongPass#2026",
            "role": "operador",
        },
    )
    assert resp.status_code == 422


# 4. Contraseñas débiles (25 tests)
@pytest.mark.parametrize(
    "weak_pw",
    [
        "",
        "Short1!",
        "1234567",
        "alllowercase1!",
        "ALLUPPERCASE1!",
        "NoDigitsHere!",
        "NoSpecialChar123",
        "Has Space1!",
        "password",
        "Password",
        "Password1",
        "12345678",
        "!@#$%^&*",
        "aB1!aB1",
        "A" * 129 + "a1!",
        "abc def1A!",
        "sinmayuscula1$",
        "SINMINUSCULA1$",
        "SinNumeroAbc$",
        "SinSimbolo123A",
        "tab\tChar1A!",
        "nl\nChar1A!",
        "1234abcd!",
        "1234ABCD!",
        "Abcdefgh",
    ],
)
def test_weak_passwords(client, weak_pw):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "validuser2",
            "email": "valid2@empresa.com",
            "password": weak_pw,
            "role": "operador",
        },
    )
    assert resp.status_code == 422


# 5. Contraseñas fuertes válidas (15 tests)
@pytest.mark.parametrize(
    "strong_pw",
    [
        "StrongPass#2026",
        "Abcdef1!",
        "My$ecret99",
        "Erp@Admin2025",
        "Z9!xY2@wQ",
        "Test_Pass_123",
        "Cloud-Lab-2026!",
        "Operador+99",
        "Auditor=2026A",
        "Val1d[Pass]",
        "Pass{Word}1",
        "Check;123A",
        "Dot.Pass123A",
        "Comma,Pass1A",
        "Slash/Pass1A",
    ],
)
def test_strong_passwords(client, strong_pw):
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "validuser3",
            "email": "valid3@empresa.com",
            "password": strong_pw,
            "role": "operador",
        },
    )
    assert resp.status_code == 201


# 6. Roles inválidos y payloads malformados (15 tests)
@pytest.mark.parametrize(
    "payload",
    [
        {"username": "u10", "email": "u10@e.com", "password": "StrongPass#2026", "role": "superadmin"},
        {"username": "u11", "email": "u11@e.com", "password": "StrongPass#2026", "role": "root"},
        {"username": "u12", "email": "u12@e.com", "password": "StrongPass#2026", "role": ""},
        {"username": "u13", "email": "u13@e.com", "password": "StrongPass#2026", "role": 123},
        {"username": "u14", "email": "u14@e.com"},
        {"username": "u15", "password": "StrongPass#2026"},
        {"email": "u16@e.com", "password": "StrongPass#2026"},
        {},
        {"username": None, "email": "u17@e.com", "password": "StrongPass#2026"},
        {"username": "u18", "email": None, "password": "StrongPass#2026"},
        {"username": "u19", "email": "u19@e.com", "password": None},
        {"username": 12345, "email": "u20@e.com", "password": "StrongPass#2026"},
        {"username": "u21", "email": "u21@e.com", "password": ["StrongPass#2026"]},
        {"username": "u22", "email": "u22@e.com", "password": "StrongPass#2026", "role": "ADMIN"},
        {"username": "u23", "email": "u23@e.com", "password": "StrongPass#2026", "role": "guest"},
    ],
)
def test_invalid_roles_and_malformed_payloads(client, payload):
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 422


# 7. Conflictos de duplicados (6 tests)
@pytest.mark.parametrize(
    ("u2", "e2"),
    [
        ("dupuser", "other1@empresa.com"),
        ("otheruser1", "dup@empresa.com"),
        ("dupuser", "dup@empresa.com"),
        ("dupuser", "DUP@EMPRESA.COM"),
        ("otheruser2", "Dup@Empresa.com"),
        ("dupuser", "another@empresa.com"),
    ],
)
def test_duplicate_user_and_email_conflicts(client, u2, e2):
    r1 = client.post(
        "/api/auth/register",
        json={
            "username": "dupuser",
            "email": "dup@empresa.com",
            "password": "StrongPass#2026",
            "role": "operador",
        },
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/auth/register",
        json={
            "username": u2,
            "email": e2,
            "password": "StrongPass#2026",
            "role": "operador",
        },
    )
    assert r2.status_code == 409


# 8. Matriz de Login válido e inválido (20 tests)
@pytest.mark.parametrize(
    ("login_id", "password", "is_active", "expected_status"),
    [
        ("loginuser", "StrongPass#2026", True, 200),
        ("login@empresa.com", "StrongPass#2026", True, 200),
        ("LOGIN@EMPRESA.COM", "StrongPass#2026", True, 200),
        (" loginuser ", "StrongPass#2026", True, 200),
        ("loginuser", "WrongPass#2026", True, 401),
        ("login@empresa.com", "WrongPass#2026", True, 401),
        ("unknownuser", "StrongPass#2026", True, 401),
        ("unknown@empresa.com", "StrongPass#2026", True, 401),
        ("loginuser", "strongpass#2026", True, 401),
        ("loginuser", "StrongPass#2025", True, 401),
        ("loginuser", " ", True, 401),
        ("loginuser", "StrongPass#2026", False, 403),
        ("login@empresa.com", "StrongPass#2026", False, 403),
        ("loginuser", "WrongPass#2026", False, 401),
        ("admin_x", "StrongPass#2026", True, 401),
        ("loginuser!", "StrongPass#2026", True, 401),
        ("loginuser", "StrongPass#2026!", True, 401),
        ("loginuser", "12345678", True, 401),
        ("login@empresa.co", "StrongPass#2026", True, 401),
        ("loginuser", "StrongPass#2026 ", True, 401),
    ],
)
def test_login_valid_and_invalid_matrix(client, db_session, login_id, password, is_active, expected_status):
    user = User(
        username="loginuser",
        email="login@empresa.com",
        hashed_password=hash_password("StrongPass#2026"),
        role="operador",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()

    resp = client.post("/api/auth/login", json={"username": login_id, "password": password})
    assert resp.status_code == expected_status
    if expected_status == 200:
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["username"] == "loginuser"


# 9. Validación de tokens JWT expirados/inválidos (15 tests)
@pytest.mark.parametrize(
    "token_case",
    [
        "missing",
        "empty_bearer",
        "invalid_string",
        "malformed_dots",
        "expired",
        "wrong_secret",
        "missing_sub",
        "non_numeric_sub",
        "nonexistent_user",
        "tampered_payload",
        "none_alg",
        "basic_auth_instead",
        "bearer_no_space",
        "null_token",
        "whitespace_token",
    ],
)
def test_jwt_token_validation_and_expiration(client, users_and_tokens, token_case):
    valid_uid = str(users_and_tokens["admin"]["user"].id)
    headers = {}

    if token_case == "missing":
        headers = {}
    elif token_case == "empty_bearer":
        headers = {"Authorization": "Bearer "}
    elif token_case == "invalid_string":
        headers = {"Authorization": "Bearer not-a-jwt"}
    elif token_case == "malformed_dots":
        headers = {"Authorization": "Bearer a.b.c"}
    elif token_case == "expired":
        tok = create_access_token({"sub": valid_uid}, expires_delta=timedelta(seconds=-10))
        headers = {"Authorization": f"Bearer {tok}"}
    elif token_case == "wrong_secret":
        tok = jwt.encode({"sub": valid_uid}, "wrong-secret-key-32-characters-long", algorithm="HS256")
        headers = {"Authorization": f"Bearer {tok}"}
    elif token_case == "missing_sub":
        tok = create_access_token({"role": "admin"})
        headers = {"Authorization": f"Bearer {tok}"}
    elif token_case == "non_numeric_sub":
        tok = create_access_token({"sub": "abc"})
        headers = {"Authorization": f"Bearer {tok}"}
    elif token_case == "nonexistent_user":
        tok = create_access_token({"sub": "999999"})
        headers = {"Authorization": f"Bearer {tok}"}
    elif token_case == "tampered_payload":
        tok = users_and_tokens["admin"]["token"]
        parts = tok.split(".")
        headers = {"Authorization": f"Bearer {parts[0]}.{parts[1]}x.{parts[2]}"}
    elif token_case == "none_alg":
        tok = jwt.encode({"sub": valid_uid}, "", algorithm="none")
        headers = {"Authorization": f"Bearer {tok}"}
    elif token_case == "basic_auth_instead":
        headers = {"Authorization": "Basic dXNlcjpwYXNz"}
    elif token_case == "bearer_no_space":
        headers = {"Authorization": f"Bearer{users_and_tokens['admin']['token']}"}
    elif token_case == "null_token":
        headers = {"Authorization": "Bearer null"}
    elif token_case == "whitespace_token":
        headers = {"Authorization": "Bearer    "}

    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 401


# 10. Matriz RBAC: 3 roles x 6 operaciones = 18 tests
@pytest.mark.parametrize("role", ["admin", "operador", "auditor"])
@pytest.mark.parametrize(
    ("method", "action", "expected_by_role"),
    [
        ("GET", "me", {"admin": 200, "operador": 200, "auditor": 200}),
        ("GET", "list_products", {"admin": 200, "operador": 200, "auditor": 200}),
        ("POST", "create_product", {"admin": 201, "operador": 201, "auditor": 403}),
        ("PUT", "update_product", {"admin": 200, "operador": 200, "auditor": 403}),
        ("DELETE", "delete_product", {"admin": 200, "operador": 403, "auditor": 403}),
        ("POST", "create_order", {"admin": 201, "operador": 201, "auditor": 403}),
    ],
)
def test_rbac_access_matrix(client, users_and_tokens, role, method, action, expected_by_role):
    admin_headers = users_and_tokens["admin"]["headers"]
    role_headers = users_and_tokens[role]["headers"]

    # Crear producto semilla como admin
    prod = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "sku": "RBAC-001",
            "name": "Producto RBAC",
            "category": "electronica",
            "price": 100.0,
            "stock": 20,
            "min_stock": 5,
        },
    ).json()

    if action == "me":
        r = client.get("/api/auth/me", headers=role_headers)
    elif action == "list_products":
        r = client.get("/api/products", headers=role_headers)
    elif action == "create_product":
        r = client.post(
            "/api/products",
            headers=role_headers,
            json={
                "sku": "RBAC-NEW",
                "name": "Nuevo",
                "category": "oficina",
                "price": 25.0,
                "stock": 10,
                "min_stock": 2,
            },
        )
    elif action == "update_product":
        r = client.put(
            f"/api/products/{prod['id']}",
            headers=role_headers,
            json={"name": "Producto Editado"},
        )
    elif action == "delete_product":
        r = client.delete(f"/api/products/{prod['id']}", headers=role_headers)
    else:  # create_order
        r = client.post(
            "/api/orders",
            headers=role_headers,
            json={"product_id": prod["id"], "order_type": "entrada", "quantity": 2},
        )

    assert r.status_code == expected_by_role[role]
