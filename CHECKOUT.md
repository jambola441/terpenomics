# Checkout flow

Customers with 1+ cart items from a dispensary that supports online orders
(`Dispensary.accepts_pickup`) can check out from the cart drawer and pay either
**by crypto via BitPay** or **in store at pickup**. All orders are pickup orders.

## Flow

```
cart drawer → Checkout → choose payment
  ├── Pay in store  → order status "placed" → confirmation at /portal/orders/{id}
  └── Pay w/ crypto → order "pending_payment" + hosted BitPay invoice
                       → browser redirected to BitPay → pays → redirected back
                       → status flips to "placed" via IPN webhook or polling
```

Order lifecycle: `pending_payment → placed → completed`, plus `cancelled`
(customer or admin) and `expired` (BitPay invoice lapsed unpaid).

## Backend

- `models.py` — `Order` / `OrderItem` (item rows snapshot name/variant/price at
  order time, since listings get rescraped).
- `services/bitpay.py` — BitPay invoice create/fetch. IPNs are verified by
  re-fetching the invoice from BitPay; the IPN body is never trusted.
- `routes/customer/orders.py` — create / list / get / cancel /
  `refresh-payment` (poll fallback when the webhook isn't reachable) and
  `POST /customer/orders/bitpay/ipn`.
- `routes/admin/orders.py` — list/get orders, move `placed → completed|cancelled`.

## Configuration (required before crypto works)

Set in `.env` (see `services/bitpay.py` for details):

| Var | Purpose |
| --- | --- |
| `BITPAY_TOKEN` | Merchant API token from the BitPay dashboard. Unset → crypto option returns 503; in-store checkout still works. |
| `BITPAY_API_BASE` | Defaults to `https://test.bitpay.com` (sandbox). Set `https://bitpay.com` for production. |
| `BITPAY_NOTIFICATION_URL` | Public URL of `/customer/orders/bitpay/ipn`. Optional — the order page polls as a fallback. |

## Decisions left open (awaiting owner spec)

- **Online-orders flag**: reusing `Dispensary.accepts_pickup` as "supports
  online orders". If those should diverge, add a dedicated column.
- **Taxes/fees**: totals are the plain sum of listing prices — no tax, tip, or
  service fee lines yet.
- **Refunds**: cancelling a paid crypto order does not auto-refund; handle via
  the BitPay dashboard.
- **Unpriced items**: allowed for in-store orders (line total blank), blocked
  for crypto since BitPay needs a fixed invoice amount.
- **Notifications**: no email/SMS to the store or customer when an order lands;
  admin `GET /admin/orders` is the store-side view for now.
- **Order expiry**: in-store orders never auto-expire; only unpaid BitPay
  invoices do (BitPay's 15-minute window).
