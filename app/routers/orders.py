"""Endpoints de movimientos/órdenes de inventario con reglas financieras y de stock."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import Order, Product, User
from app.schemas import OrderCreate, OrderOut

router = APIRouter(prefix="/api/orders", tags=["Órdenes"])

TAX_RATE = 0.16


def calculate_discount_rate(quantity: int) -> float:
    """Calcula la tasa de descuento por volumen según la cantidad."""
    if quantity >= 50:
        return 0.15
    if quantity >= 20:
        return 0.10
    if quantity >= 10:
        return 0.05
    return 0.0


def calculate_order_totals(unit_price: float, quantity: int) -> dict[str, float]:
    """Calcula subtotal, descuento por volumen, IVA (16%) y total."""
    subtotal = round(unit_price * quantity, 2)
    discount_rate = calculate_discount_rate(quantity)
    discount_amount = round(subtotal * discount_rate, 2)
    taxable_amount = round(subtotal - discount_amount, 2)
    tax_amount = round(taxable_amount * TAX_RATE, 2)
    total = round(taxable_amount + tax_amount, 2)
    return {
        "subtotal": subtotal,
        "discount_rate": discount_rate,
        "discount_amount": discount_amount,
        "tax_rate": TAX_RATE,
        "tax_amount": tax_amount,
        "total": total,
    }


def _to_order_out(order: Order, product: Product) -> OrderOut:
    return OrderOut(
        id=order.id,
        order_type=order.order_type,
        product_id=order.product_id,
        product_sku=product.sku,
        product_name=product.name,
        user_id=order.user_id,
        quantity=order.quantity,
        unit_price=order.unit_price,
        subtotal=order.subtotal,
        discount_rate=order.discount_rate,
        discount_amount=order.discount_amount,
        tax_rate=order.tax_rate,
        tax_amount=order.tax_amount,
        total=order.total,
        notes=order.notes,
        created_at=order.created_at,
    )


@router.get("", response_model=list[OrderOut])
def list_orders(
    order_type: str | None = Query(default=None),
    product_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[OrderOut]:
    """Lista los movimientos/órdenes de inventario."""
    query = db.query(Order, Product).join(Product, Order.product_id == Product.id)
    if order_type:
        query = query.filter(Order.order_type == order_type)
    if product_id is not None:
        query = query.filter(Order.product_id == product_id)

    rows = query.order_by(Order.id.desc()).all()
    return [_to_order_out(order, product) for order, product in rows]


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "operador")),
) -> OrderOut:
    """Registra una entrada o salida de inventario de forma transaccional."""
    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado"
        )
    if not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pueden registrar movimientos para un producto inactivo",
        )

    if payload.order_type == "salida":
        if payload.quantity > product.stock:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Stock insuficiente: disponible {product.stock}, "
                    f"solicitado {payload.quantity}"
                ),
            )
        product.stock -= payload.quantity
    else:
        product.stock += payload.quantity

    totals = calculate_order_totals(product.price, payload.quantity)
    order = Order(
        order_type=payload.order_type,
        product_id=product.id,
        user_id=current_user.id,
        quantity=payload.quantity,
        unit_price=product.price,
        subtotal=totals["subtotal"],
        discount_rate=totals["discount_rate"],
        discount_amount=totals["discount_amount"],
        tax_rate=totals["tax_rate"],
        tax_amount=totals["tax_amount"],
        total=totals["total"],
        notes=payload.notes.strip(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    db.refresh(product)
    return _to_order_out(order, product)
