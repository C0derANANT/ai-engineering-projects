"""Demo orders: loading from data/sample_orders.json, order ID clean-up and lookups."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .calculators import (
    LATE_FREE_CANCEL_MINUTES,
    NO_PARTNER_FREE_CANCEL_MINUTES,
    PAYMENT_METHODS,
    STATUS_LABELS,
    D,
    Order,
    OrderItem,
    delivery_fee,
    money,
    on_time_promise,
)

_DECIMAL_FIELDS = (
    "packaging",
    "coupon_discount",
    "delivery_fee",
    "small_cart_fee",
    "high_demand_fee",
    "late_night_fee",
    "tip",
    "cravecart_money_used",
)
_PASSTHROUGH_FIELDS = (
    "coupon_code",
    "plus_member",
    "partner_assigned",
    "partner_at_restaurant",
    "food_ready_minutes_ago",
    "delivered_minutes_ago",
    "scheduled_slot_in_minutes",
)


def normalize_order_id(raw) -> str | None:
    """Accept '#1042', 'order 1042', 'CC-1042' or ' 1042 ' and return '1042'."""
    match = re.search(r"\d{3,8}", str(raw or ""))
    return match.group(0) if match else None


def _parse_order(data: dict) -> Order:
    order_id = normalize_order_id(data.get("order_id"))
    if not order_id:
        raise ValueError(f"Order has no valid order_id: {data!r}")
    where = f"order {order_id}"

    items = []
    for raw in data.get("items") or []:
        price, qty = D(raw.get("price", -1)), int(raw.get("quantity", 0))
        if not raw.get("name") or price < 0 or qty < 1:
            raise ValueError(f"{where}: every item needs a name, a price >= 0 and a quantity >= 1")
        items.append(OrderItem(name=str(raw["name"]), price=price, quantity=qty))
    if not items:
        raise ValueError(f"{where}: an order needs at least one item")

    status = data.get("status")
    if status not in STATUS_LABELS:
        raise ValueError(f"{where}: unknown status {status!r} (expected one of {sorted(STATUS_LABELS)})")
    method = data.get("payment_method")
    if method not in PAYMENT_METHODS:
        raise ValueError(f"{where}: unknown payment_method {method!r} (expected one of {sorted(PAYMENT_METHODS)})")

    order = Order(
        order_id=order_id,
        customer_name=str(data.get("customer_name", "Customer")),
        restaurant=str(data.get("restaurant", "Restaurant")),
        items=items,
        distance_km=D(data.get("distance_km", 0)),
        payment_method=method,
        status=status,
        placed_minutes_ago=float(data.get("placed_minutes_ago", 0)),
        promised_minutes=float(data.get("promised_minutes", 0)),
        **{f: D(data[f]) for f in _DECIMAL_FIELDS if f in data},
        **{f: data[f] for f in _PASSTHROUGH_FIELDS if f in data},
    )

    # Keep the demo data honest: the stored delivery fee must follow the pricing rules
    expected = delivery_fee(order.distance_km)
    plus_free = order.plus_member and order.item_total >= 199 and order.distance_km <= 7
    if order.delivery_fee not in (expected, 0 if plus_free else expected):
        raise ValueError(
            f"{where}: delivery_fee ₹{order.delivery_fee} doesn't match ₹{expected} for {order.distance_km} km"
        )
    if order.cravecart_money_used > order.total:
        raise ValueError(f"{where}: cravecart_money_used is more than the order total")
    return order


class OrderStore:
    """All demo orders, looked up by ID."""

    def __init__(self, orders: list[Order], scenarios: dict[str, str] | None = None):
        self._orders = {o.order_id: o for o in orders}
        self.scenarios = scenarios or {}

    @classmethod
    def from_file(cls, path: Path) -> OrderStore:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Demo orders file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} isn't valid JSON: {exc}") from exc
        records = raw.get("orders", []) if isinstance(raw, dict) else raw
        orders = [_parse_order(r) for r in records]
        ids = [o.order_id for o in orders]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{path} has duplicate order IDs")
        scenarios = {normalize_order_id(r["order_id"]): r.get("scenario", "") for r in records}
        return cls(orders, scenarios)

    def ids(self) -> list[str]:
        return sorted(self._orders)

    def get(self, raw_id) -> Order | None:
        order_id = normalize_order_id(raw_id)
        return self._orders.get(order_id) if order_id else None

    def not_found(self, raw_id) -> dict:
        return {
            "found": False,
            "error": f"No demo order matches '{raw_id}'. This demo only has these orders: "
            + ", ".join(f"#{i}" for i in self.ids()),
        }

    def summary(self, order: Order) -> dict:
        """Everything the assistant may say about an order."""
        late = order.minutes_late
        info = {
            "found": True,
            "order_id": order.order_id,
            "customer_first_name": order.customer_name.split()[0],
            "restaurant": order.restaurant,
            "status": STATUS_LABELS[order.status],
            "items": [f"{i.quantity} × {i.name} (₹{money(i.price):.2f} each)" for i in order.items],
            "bill": order.bill(),
            "payment_method": order.payment_method,
            "plus_member": order.plus_member,
            "placed": f"{order.placed_minutes_ago:g} minutes ago",
            "snapshot_note": "Demo data: times are a frozen snapshot.",
        }
        if order.coupon_code:
            info["coupon"] = f"{order.coupon_code} (−₹{money(order.coupon_discount):.2f})"
        if order.cravecart_money_used:
            info["paid_with_cravecart_money"] = money(order.cravecart_money_used)
        if order.scheduled_slot_in_minutes is not None:
            info["scheduled_slot"] = f"starts in {order.scheduled_slot_in_minutes:g} minutes"
        else:
            info["promised_delivery"] = f"within {order.promised_minutes:g} minutes of ordering"
            info["minutes_past_promised_time"] = round(late, 1)
        if order.status == "delivered":
            info["delivered"] = f"{order.delivered_minutes_ago:g} minutes ago"
        if order.item_total >= 1000:
            info["delivery_pin"] = "Required (item total ₹1,000 or more). Share it only when the food is in hand."
        if order.status not in ("delivered", "cancelled", "undelivered"):
            if late > LATE_FREE_CANCEL_MINUTES:
                info["free_cancellation"] = "Available: more than 30 minutes past the promised time."
            elif (
                order.status == "ready"
                and not order.partner_assigned
                and (order.food_ready_minutes_ago or 0) >= NO_PARTNER_FREE_CANCEL_MINUTES
            ):
                info["free_cancellation"] = "Available: no delivery partner 20+ minutes after the food was ready."
        promise = on_time_promise(order)
        if promise:
            info["plus_on_time_promise"] = promise
        return info

    def table(self) -> list[list[str]]:
        """Rows for the 'Demo orders' panel in the app."""
        return [
            [f"#{o.order_id}", o.restaurant, STATUS_LABELS[o.status].split(" (")[0], self.scenarios.get(o.order_id, "")]
            for o in (self._orders[i] for i in self.ids())
        ]
