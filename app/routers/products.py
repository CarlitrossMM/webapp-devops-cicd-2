"""Endpoints CRUD de productos, filtros y alertas de stock bajo."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import Order, Product, User
from app.schemas import ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/api/products", tags=["Productos"])


def _to_product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        description=product.description,
        category=product.category,
        price=product.price,
        stock=product.stock,
        min_stock=product.min_stock,
        is_active=product.is_active,
        low_stock=product.stock <= product.min_stock,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("", response_model=list[ProductOut])
def list_products(
    category: str | None = Query(default=None),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    search: str | None = Query(default=None),
    low_stock_only: bool = Query(default=False),
    active_only: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ProductOut]:
    """Lista productos con filtros dinámicos."""
    query = db.query(Product)

    if category:
        query = query.filter(Product.category == category)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if active_only is not None:
        query = query.filter(Product.is_active == active_only)
    if low_stock_only:
        query = query.filter(Product.stock <= Product.min_stock)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.sku.ilike(term),
                Product.name.ilike(term),
                Product.description.ilike(term),
            )
        )

    products = query.order_by(Product.id.desc()).all()
    return [_to_product_out(p) for p in products]


@router.get("/alerts/low-stock", response_model=list[ProductOut])
def low_stock_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ProductOut]:
    """Retorna productos activos cuyo stock es menor o igual al mínimo."""
    products = (
        db.query(Product)
        .filter(Product.is_active.is_(True), Product.stock <= Product.min_stock)
        .order_by(Product.stock.asc())
        .all()
    )
    return [_to_product_out(p) for p in products]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProductOut:
    """Obtiene un producto por su ID."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    return _to_product_out(product)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "operador")),
) -> ProductOut:
    """Crea un nuevo producto validando SKU único."""
    existing = db.query(Product).filter(Product.sku == payload.sku).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un producto con el SKU '{payload.sku}'",
        )

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return _to_product_out(product)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "operador")),
) -> ProductOut:
    """Actualiza un producto existente."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    update_data = payload.model_dump(exclude_unset=True)
    if "sku" in update_data and update_data["sku"] != product.sku:
        dup = db.query(Product).filter(Product.sku == update_data["sku"]).first()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe otro producto con el SKU '{update_data['sku']}'",
            )

    for key, value in update_data.items():
        setattr(product, key, value)

    db.commit()
    db.refresh(product)
    return _to_product_out(product)


@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict[str, str]:
    """Elimina un producto (solo rol admin)."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

    has_orders = db.query(Order).filter(Order.product_id == product_id).first()
    if has_orders:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar un producto con movimientos registrados",
        )

    db.delete(product)
    db.commit()
    return {"detail": "Producto eliminado correctamente"}
