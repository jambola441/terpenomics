from models import Customer, Listing, Purchase, PurchaseItem


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


def serialize_purchase_item(item: PurchaseItem, listing: Listing) -> dict:
    return {
        "id": str(item.id),
        "purchase_id": str(item.purchase_id),
        "listing_id": str(item.listing_id) if item.listing_id else None,
        "product_name": listing.scraped_name if listing else None,
        "dispensary_id": str(listing.dispensary_id) if listing else None,
        "variant": listing.variant if listing else None,
        "quantity": item.quantity,
        "line_amount_cents": item.line_amount_cents,
        "feedback": item.feedback,
        "feedback_at": item.feedback_at.isoformat() if item.feedback_at else None,
    }
