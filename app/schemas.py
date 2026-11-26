"""Esquemas Pydantic v2 con validaciones estrictas de dominio."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

VALID_ROLES = ("admin", "operador", "auditor")
VALID_CATEGORIES = ("electronica", "oficina", "herramientas", "insumos")
VALID_ORDER_TYPES = ("entrada", "salida")

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,28}[a-zA-Z0-9]$")
SKU_REGEX = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,30}[A-Z0-9]$")
SPECIAL_CHAR_REGEX = re.compile(r"[!@#$%^&*()_+\-=\[\]{}|;:',.<>?/\\]")


def validate_password_strength(password: str) -> str:
    """Valida complejidad mínima de contraseña."""
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if len(password) > 128:
        raise ValueError("La contraseña no puede superar los 128 caracteres")
    if any(c.isspace() for c in password):
        raise ValueError("La contraseña no puede contener espacios")
    if not any(c.isupper() for c in password):
        raise ValueError("La contraseña debe incluir al menos una letra mayúscula")
    if not any(c.islower() for c in password):
        raise ValueError("La contraseña debe incluir al menos una letra minúscula")
    if not any(c.isdigit() for c in password):
        raise ValueError("La contraseña debe incluir al menos un dígito")
    if not SPECIAL_CHAR_REGEX.search(password):
        raise ValueError("La contraseña debe incluir al menos un carácter especial")
    return password


class UserRegister(BaseModel):
    """Payload para registro de usuarios."""

    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: Literal["admin", "operador", "auditor"] = "operador"

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_REGEX.match(v):
            raise ValueError(
                "El usuario debe tener 3-30 caracteres alfanuméricos, '_' o '-' "
                "(sin iniciar ni terminar en símbolo)"
            )
        return v

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: EmailStr) -> str:
        return str(v).strip().lower()

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserLogin(BaseModel):
    """Payload para inicio de sesión."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    """Representación pública de usuario."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Respuesta de autenticación JWT."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProductCreate(BaseModel):
    """Payload para creación de producto."""

    sku: str = Field(..., min_length=3, max_length=32)
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    category: Literal["electronica", "oficina", "herramientas", "insumos"]
    price: float = Field(..., gt=0, le=1_000_000)
    stock: int = Field(default=0, ge=0, le=1_000_000)
    min_stock: int = Field(default=5, ge=0, le=1_000_000)
    is_active: bool = True

    @field_validator("sku")
    @classmethod
    def check_sku(cls, v: str) -> str:
        normalized = v.strip().upper()
        if not SKU_REGEX.match(normalized):
            raise ValueError(
                "El SKU debe tener 3-32 caracteres (letras, números o guiones, "
                "sin iniciar ni terminar en guion)"
            )
        return normalized

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres visibles")
        return cleaned


class ProductUpdate(BaseModel):
    """Payload para actualización parcial de producto."""

    sku: str | None = Field(default=None, min_length=3, max_length=32)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: Literal["electronica", "oficina", "herramientas", "insumos"] | None = None
    price: float | None = Field(default=None, gt=0, le=1_000_000)
    stock: int | None = Field(default=None, ge=0, le=1_000_000)
    min_stock: int | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None

    @field_validator("sku")
    @classmethod
    def check_sku(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip().upper()
        if not SKU_REGEX.match(normalized):
            raise ValueError(
                "El SKU debe tener 3-32 caracteres (letras, números o guiones, "
                "sin iniciar ni terminar en guion)"
            )
        return normalized

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres visibles")
        return cleaned


class ProductOut(BaseModel):
    """Representación de producto con bandera de bajo stock."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str
    category: str
    price: float
    stock: int
    min_stock: int
    is_active: bool
    low_stock: bool
    created_at: datetime
    updated_at: datetime


class OrderCreate(BaseModel):
    """Payload para registrar una entrada o salida de inventario."""

    product_id: int = Field(..., gt=0)
    order_type: Literal["entrada", "salida"]
    quantity: int = Field(..., gt=0, le=100_000)
    notes: str = Field(default="", max_length=255)


class OrderOut(BaseModel):
    """Representación de orden con desglose financiero."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_type: str
    product_id: int
    product_sku: str
    product_name: str
    user_id: int
    quantity: int
    unit_price: float
    subtotal: float
    discount_rate: float
    discount_amount: float
    tax_rate: float
    tax_amount: float
    total: float
    notes: str
    created_at: datetime
