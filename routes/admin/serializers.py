from models import Customer, Product, Purchase


def serialize_customer(c: Customer) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "marketing_opt_in": c.marketing_opt_in,
        "last_visit_at": c.last_visit_at.isoformat() if c.last_visit_at else None,
        "auth_user_id": str(c.auth_user_id) if getattr(c, "auth_user_id", None) else None,
    }


def serialize_product(p: Product, terpenes: list) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "brand": p.brand,
        "category": p.category,
        "is_active": p.is_active,
        "terpenes": terpenes,
    }


def serialize_purchase(p: Purchase) -> dict:
    return {
        "id": str(p.id),
        "customer_id": str(p.customer_id),
        "purchased_at": p.purchased_at.isoformat(),
        "total_amount_cents": p.total_amount_cents,
        "source": p.source,
        "external_id": getattr(p, "external_id", None),
        "notes": p.notes,
    }
