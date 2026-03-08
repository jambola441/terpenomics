from models import Customer, Product, Purchase, PurchaseItem


def serialize_customer(c: Customer) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "marketing_opt_in": c.marketing_opt_in,
        "last_visit_at": c.last_visit_at.isoformat() if c.last_visit_at else None,
        "auth_user_id": str(c.auth_user_id) if c.auth_user_id else None,
    }


def serialize_product(p: Product, terpenes: list, cannabinoids: list = []) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "brand": p.brand,
        "category": p.category,
        "is_active": p.is_active,
        "terpenes": terpenes,
        "cannabinoids": cannabinoids,
    }


def serialize_purchase(p: Purchase) -> dict:
    return {
        "id": str(p.id),
        "customer_id": str(p.customer_id),
        "purchased_at": p.purchased_at.isoformat(),
        "total_amount_cents": p.total_amount_cents,
        "source": p.source,
        "external_id": p.external_id,
        "notes": p.notes,
    }


def serialize_purchase_item(item: PurchaseItem, product_name: str) -> dict:
    return {
        "id": str(item.id),
        "purchase_id": str(item.purchase_id),
        "product_id": str(item.product_id),
        "product_name": product_name,
        "quantity": item.quantity,
        "line_amount_cents": item.line_amount_cents,
        "feedback": item.feedback,
        "feedback_at": item.feedback_at.isoformat() if item.feedback_at else None,
    }
