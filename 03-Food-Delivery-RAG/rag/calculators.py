"""Exact money maths for CraveCart's fee, cancellation and refund policies.

The LLM never does arithmetic itself: it calls these functions (through tools.py) and
reports their numbers. Every rule here mirrors a document in knowledge-base/:

- company/pricing-fees-and-membership.md  -> estimate_bill(), delivery_fee()
- policies/cancellation-policy.md          -> cancellation_quote()
- policies/refund-policy.md                -> item_refund()

Money is calculated with Decimal so ₹ amounts never pick up float rounding errors.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

# --- Pricing (company/pricing-fees-and-membership.md) -----------------------------------
FOOD_GST = Decimal("0.05")
FEE_GST = Decimal("0.18")
BASE_DELIVERY_FEE = Decimal(20)
BASE_DELIVERY_KM = Decimal(3)
PER_EXTRA_KM = Decimal(8)
MAX_DELIVERY_FEE = Decimal(70)
MAX_DELIVERY_KM = Decimal(10)
PLUS_FREE_DELIVERY_MIN_ITEM_TOTAL = Decimal(199)
PLUS_FREE_DELIVERY_MAX_KM = Decimal(7)
SMALL_CART_THRESHOLD = Decimal(149)
SMALL_CART_FEE = Decimal(25)
PLATFORM_FEE = Decimal(6)
LATE_NIGHT_FEE = Decimal(15)
MAX_HIGH_DEMAND_FEE = Decimal(40)
PLUS_HIGH_DEMAND_CAP = Decimal(20)
MAX_TIP = Decimal(500)

# --- Time windows (policies/cancellation-policy.md, policies/refund-policy.md) ----------
GRACE_PERIOD_MINUTES = 1
LATE_FREE_CANCEL_MINUTES = 30
NO_PARTNER_FREE_CANCEL_MINUTES = 20
SCHEDULED_FREE_CANCEL_MINUTES = 60
ITEM_ISSUE_WINDOW_MINUTES = 3 * 60
FOOD_SAFETY_WINDOW_MINUTES = 24 * 60
NOT_RECEIVED_WINDOW_MINUTES = 24 * 60
REPLACEMENT_WINDOW_MINUTES = 45
PLUS_ON_TIME_PROMISE_MINUTES = 10
PLUS_ON_TIME_CREDIT = Decimal(50)

REFUND_TIMELINES = {
    "CraveCart Money": "instant (within 10 minutes)",
    "UPI": "1–3 business days",
    "Debit card": "5–7 business days",
    "Credit card": "5–7 business days",
    "Net banking": "5–7 business days",
    "Wallet": "1–3 business days",
    "Pay Later": "3–5 business days",
    "COD": "instant to CraveCart Money, or 3–5 business days to your UPI ID or bank account",
}

PAYMENT_METHODS = set(REFUND_TIMELINES)

# Order statuses, in the order an order moves through them
STATUS_LABELS = {
    "scheduled": "Scheduled (not yet sent to the restaurant)",
    "waiting_for_restaurant": "Waiting for restaurant to accept",
    "confirmed": "Order confirmed (restaurant accepted, not yet preparing)",
    "preparing": "Preparing",
    "ready": "Food ready, waiting for pickup",
    "picked_up": "Picked up / on the way",
    "arriving": "Arriving",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
    "undelivered": "Undelivered",
}
NOT_PICKED_UP = {"scheduled", "waiting_for_restaurant", "confirmed", "preparing", "ready"}
STAGE_D_STATUSES = {"preparing", "ready", "picked_up", "arriving"}
CLOSED_STATUSES = {"delivered", "cancelled", "undelivered"}

ISSUE_TYPES = {"missing", "wrong", "damaged", "quality", "foreign_object", "not_received"}


def D(value) -> Decimal:
    """Convert to Decimal via str, so 5.2 stays exactly 5.2."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def money(value: Decimal) -> float:
    """Round to paise (2 decimals, half-up) for display."""
    return float(D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _r(value: Decimal) -> Decimal:
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PolicyError(ValueError):
    """Raised for inputs the policy can't price (for example, a 12 km delivery)."""


# =========================================================================================
# Orders
# =========================================================================================
@dataclass
class OrderItem:
    name: str
    price: Decimal
    quantity: int

    @property
    def value(self) -> Decimal:
        return self.price * self.quantity


@dataclass
class Order:
    """One demo order. Times are a frozen snapshot ("minutes ago"), so demos are repeatable."""

    order_id: str
    customer_name: str
    restaurant: str
    items: list[OrderItem]
    distance_km: Decimal
    payment_method: str
    status: str
    placed_minutes_ago: float
    promised_minutes: float
    packaging: Decimal = Decimal(0)
    coupon_code: str | None = None
    coupon_discount: Decimal = Decimal(0)
    delivery_fee: Decimal = Decimal(0)
    platform_fee: Decimal = PLATFORM_FEE
    small_cart_fee: Decimal = Decimal(0)
    high_demand_fee: Decimal = Decimal(0)
    late_night_fee: Decimal = Decimal(0)
    tip: Decimal = Decimal(0)
    cravecart_money_used: Decimal = Decimal(0)
    plus_member: bool = False
    partner_assigned: bool = False
    partner_at_restaurant: bool = False
    food_ready_minutes_ago: float | None = None
    delivered_minutes_ago: float | None = None
    scheduled_slot_in_minutes: float | None = None
    notes: list[str] = field(default_factory=list)

    # ---- bill ----------------------------------------------------------------------------
    @property
    def item_total(self) -> Decimal:
        return sum((i.value for i in self.items), Decimal(0))

    @property
    def food_taxable(self) -> Decimal:
        """Food + packaging after discounts: the base for 5% GST (pricing doc, section 8)."""
        return self.item_total + self.packaging - self.coupon_discount

    @property
    def food_gst(self) -> Decimal:
        return _r(self.food_taxable * FOOD_GST)

    @property
    def fees(self) -> Decimal:
        return (
            self.delivery_fee
            + self.platform_fee
            + self.small_cart_fee
            + self.high_demand_fee
            + self.late_night_fee
        )

    @property
    def fees_gst(self) -> Decimal:
        return _r(self.fees * FEE_GST)

    @property
    def total(self) -> Decimal:
        return self.food_taxable + self.food_gst + self.fees + self.fees_gst + self.tip

    @property
    def paid_upfront(self) -> Decimal:
        """COD orders are paid at the door, except any CraveCart Money already used."""
        return self.cravecart_money_used if self.payment_method == "COD" else self.total

    @property
    def minutes_late(self) -> float:
        """How far past the promised time (upper ETA at checkout) the order is or was."""
        if self.scheduled_slot_in_minutes is not None:
            return 0.0
        elapsed = self.placed_minutes_ago
        if self.status == "delivered" and self.delivered_minutes_ago is not None:
            elapsed = self.placed_minutes_ago - self.delivered_minutes_ago
        return max(0.0, elapsed - self.promised_minutes)

    def bill(self) -> dict:
        lines = {
            "item_total": money(self.item_total),
            "packaging": money(self.packaging),
            "coupon_discount": -money(self.coupon_discount),
            "delivery_fee": money(self.delivery_fee),
            "platform_fee": money(self.platform_fee),
            "small_cart_fee": money(self.small_cart_fee),
            "high_demand_fee": money(self.high_demand_fee),
            "late_night_fee": money(self.late_night_fee),
            "gst_on_food_5pct": money(self.food_gst),
            "gst_on_fees_18pct": money(self.fees_gst),
            "tip": money(self.tip),
            "total": money(self.total),
        }
        return {k: v for k, v in lines.items() if v != 0 or k in ("item_total", "total")}


def _split_refund(order: Order, amount: Decimal) -> dict:
    """Refunds go to CraveCart Money first (up to what was paid from it), the rest to source."""
    amount = _r(max(amount, Decimal(0)))
    to_wallet = min(amount, order.cravecart_money_used)
    to_source = amount - to_wallet
    split = {}
    if to_wallet:
        split["CraveCart Money"] = money(to_wallet)
    if to_source:
        method = "CraveCart Money (default for COD)" if order.payment_method == "COD" else order.payment_method
        split[method] = money(to_source)
    return split


def _timeline(order: Order) -> str:
    parts = []
    if order.cravecart_money_used:
        parts.append(f"CraveCart Money part: {REFUND_TIMELINES['CraveCart Money']}")
    parts.append(f"{order.payment_method} part: {REFUND_TIMELINES.get(order.payment_method, '5–7 business days')}")
    parts.append("You can also choose an instant refund to CraveCart Money instead.")
    return "; ".join(parts)


# =========================================================================================
# Pricing
# =========================================================================================
def delivery_fee(distance_km) -> Decimal:
    """₹20 for the first 3 km, then ₹8 per km charged per 100 m, capped at ₹70."""
    distance = D(distance_km)
    if distance.is_nan() or distance < 0:
        raise PolicyError("Distance must be a positive number of kilometres.")
    if distance > MAX_DELIVERY_KM:
        raise PolicyError(
            f"{distance} km is beyond CraveCart's maximum delivery distance of 10 km "
            "(7 km in dense zones of Mumbai, Bengaluru and Delhi NCR)."
        )
    extra = max(Decimal(0), distance - BASE_DELIVERY_KM)
    extra_rounded = (extra * 10).to_integral_value(rounding=ROUND_CEILING) / 10  # per 100 m
    return min(BASE_DELIVERY_FEE + PER_EXTRA_KM * extra_rounded, MAX_DELIVERY_FEE)


def estimate_bill(
    item_total,
    distance_km,
    packaging=0,
    plus_member: bool = False,
    high_demand_fee=0,
    late_night: bool = False,
    coupon_discount=0,
    tip=0,
) -> dict:
    """Price a hypothetical order line by line, as on the CraveCart checkout screen."""
    item_total, packaging = D(item_total), D(packaging)
    high_demand, coupon, tip = D(high_demand_fee), D(coupon_discount), D(tip)
    notes = []

    if item_total <= 0:
        raise PolicyError("The item total must be more than ₹0.")
    if packaging < 0 or coupon < 0 or tip < 0 or high_demand < 0:
        raise PolicyError("Amounts can't be negative.")
    if coupon > item_total:
        raise PolicyError("A coupon discount can't be larger than the item total.")
    if tip > MAX_TIP:
        raise PolicyError("Tips can be at most ₹500.")
    if high_demand > MAX_HIGH_DEMAND_FEE:
        raise PolicyError("The high-demand fee is between ₹10 and ₹40.")
    if 0 < high_demand < 10:
        notes.append("High-demand fees start at ₹10; using ₹10.")
        high_demand = Decimal(10)

    distance = D(distance_km)
    fee = delivery_fee(distance)
    if plus_member and item_total >= PLUS_FREE_DELIVERY_MIN_ITEM_TOTAL and distance <= PLUS_FREE_DELIVERY_MAX_KM:
        notes.append("CraveCart Plus: delivery fee waived (item total ₹199+ within 7 km).")
        fee = Decimal(0)
    elif plus_member:
        notes.append(
            "CraveCart Plus free delivery doesn't apply: it needs an item total of ₹199 or more "
            "and a restaurant within 7 km."
        )
    if plus_member and high_demand > PLUS_HIGH_DEMAND_CAP:
        notes.append("CraveCart Plus caps the high-demand fee at ₹20.")
        high_demand = PLUS_HIGH_DEMAND_CAP

    small_cart = SMALL_CART_FEE if item_total < SMALL_CART_THRESHOLD else Decimal(0)
    if small_cart:
        notes.append("Small cart fee of ₹25 added because the item total is below ₹149.")
    late = LATE_NIGHT_FEE if late_night else Decimal(0)

    food_taxable = item_total + packaging - coupon
    food_gst = _r(food_taxable * FOOD_GST)
    fees = fee + PLATFORM_FEE + small_cart + high_demand + late
    fees_gst = _r(fees * FEE_GST)
    total = food_taxable + food_gst + fees + fees_gst + tip

    lines = {
        "item_total": money(item_total),
        "packaging": money(packaging),
        "coupon_discount": -money(coupon),
        "delivery_fee": money(fee),
        "platform_fee": money(PLATFORM_FEE),
        "small_cart_fee": money(small_cart),
        "high_demand_fee": money(high_demand),
        "late_night_fee": money(late),
        "gst_on_food_5pct": money(food_gst),
        "gst_on_fees_18pct": money(fees_gst),
        "tip": money(tip),
    }
    return {
        "bill": {k: v for k, v in lines.items() if v != 0 or k in ("item_total", "delivery_fee", "platform_fee")},
        "total": money(total),
        "notes": notes,
        "policy_source": "company/pricing-fees-and-membership.md",
    }


# =========================================================================================
# Cancellation (policies/cancellation-policy.md)
# =========================================================================================
def cancellation_quote(order: Order) -> dict:
    """What the customer would pay and get back if they cancelled this order right now."""
    result = {
        "order_id": order.order_id,
        "status": STATUS_LABELS.get(order.status, order.status),
        "payment_method": order.payment_method,
        "order_total": money(order.total),
        "policy_source": "policies/cancellation-policy.md",
        "note": "This is a quote only. The assistant can't cancel orders; the customer cancels in the app.",
    }

    if order.status == "delivered":
        return result | {
            "can_cancel": False,
            "reason": "The order has already been delivered, so it can't be cancelled. "
            "If something was wrong with it, report it under Help > select order (refund policy).",
        }
    if order.status in ("cancelled", "undelivered"):
        return result | {"can_cancel": False, "reason": f"The order is already {order.status}."}

    free_reason = None
    if order.scheduled_slot_in_minutes is not None and order.scheduled_slot_in_minutes > SCHEDULED_FREE_CANCEL_MINUTES:
        free_reason = (
            f"Scheduled order with the slot {order.scheduled_slot_in_minutes:g} minutes away: "
            "free cancellation until 60 minutes before the slot."
        )
    elif order.placed_minutes_ago <= GRACE_PERIOD_MINUTES:
        free_reason = "Within the 60-second grace period after placing the order (stage A)."
    elif order.minutes_late > LATE_FREE_CANCEL_MINUTES:
        free_reason = (
            f"The order is {order.minutes_late:g} minutes past the promised delivery time, "
            "more than 30 minutes late, so cancellation is free at any stage (exception 1)."
        )
    elif (
        order.status == "ready"
        and not order.partner_assigned
        and (order.food_ready_minutes_ago or 0) >= NO_PARTNER_FREE_CANCEL_MINUTES
    ):
        free_reason = (
            f"The food has been ready for {order.food_ready_minutes_ago:g} minutes with no delivery "
            "partner assigned (20+ minutes), so cancellation is free (exception 2)."
        )
    elif order.status == "waiting_for_restaurant":
        free_reason = "The restaurant hasn't accepted the order yet (stage B)."

    if free_reason:
        refund = order.paid_upfront
        return result | {
            "can_cancel": True,
            "stage": "free",
            "reason": free_reason,
            "cancellation_fee": 0.0,
            "refund_total": money(refund),
            "refund_to": _split_refund(order, refund),
            "coupon_restored": bool(order.coupon_code),
            "tip_refunded": bool(order.tip),
            "outstanding_dues": 0.0,
            "refund_timeline": _timeline(order) if refund else "Nothing was paid upfront (COD).",
            "how_to_cancel": "Tracking screen > Cancel order (or the 'Cancel for free' banner when it appears).",
        }

    if order.status in ("confirmed", "scheduled"):
        # Stage C: 50% of food value after discounts, plus the GST on that half.
        # A scheduled order within 60 minutes of its slot is also charged at stage C.
        food_fee = _r(order.food_taxable * Decimal("0.5"))
        fee_food_gst = _r(food_fee * FOOD_GST)
        kept_fees = order.platform_fee + order.small_cart_fee
        delivery_like = order.delivery_fee + order.high_demand_fee + order.late_night_fee
        if order.partner_at_restaurant:
            kept_fees += delivery_like
            delivery_note = "A delivery partner is already at the restaurant, so delivery-related fees are kept."
        else:
            delivery_note = "No delivery partner has reached the restaurant, so delivery-related fees are refunded."
        kept = food_fee + fee_food_gst + kept_fees + _r(kept_fees * FEE_GST)
        refundable = order.total - kept  # includes the tip
        stage = "C"
        reason = (
            "The restaurant has accepted but not started preparing (stage C): the fee is 50% of "
            f"item total and packaging after discounts (₹{money(food_fee):.2f}) plus its GST; the platform "
            f"fee and any small cart fee are kept. {delivery_note} The tip is refunded."
        )
    elif order.status in STAGE_D_STATUSES:
        tip_back = order.tip if order.status in NOT_PICKED_UP else Decimal(0)
        kept = order.total - tip_back
        refundable = tip_back
        stage = "D"
        reason = (
            "The restaurant has started preparing (stage D): the cancellation fee is 100% of the order. "
            + (
                "The tip is refunded because the order hasn't been picked up."
                if tip_back
                else "Nothing is refunded (the order has been picked up or had no tip)."
            )
        )
    else:  # unknown status: never guess money
        return result | {"can_cancel": False, "reason": f"Unknown order status '{order.status}'."}

    is_cod = order.payment_method == "COD"
    refund = max(Decimal(0), order.paid_upfront - kept) if is_cod else refundable
    dues = max(Decimal(0), kept - order.paid_upfront) if is_cod else Decimal(0)
    return result | {
        "can_cancel": True,
        "stage": stage,
        "reason": reason,
        "cancellation_fee": money(kept),
        "refund_total": money(refund),
        "refund_to": _split_refund(order, refund),
        "coupon_restored": False,
        "tip_refunded": bool(order.tip) and refundable >= order.tip > 0,
        "outstanding_dues": money(dues),
        "dues_note": (
            "COD order: the fee becomes outstanding dues, payable online with the next order. "
            "Two refused or unpaid COD orders in 90 days disable COD for 180 days."
            if dues
            else None
        ),
        "refund_timeline": _timeline(order) if refund else None,
        "how_to_cancel": "Help (or 'Need help?') > select order > 'I want to cancel'. The fee is fixed when you confirm.",
        "waiver_note": "A stage C fee can be waived once per 12 months for accounts older than 6 months with no abuse flags.",
    }


# =========================================================================================
# Refunds for problems with delivered orders (policies/refund-policy.md)
# =========================================================================================
def match_item(order: Order, name: str) -> tuple[OrderItem | None, list[str]]:
    """Find an item by name: exact, then partial, then fuzzy. Returns (item, suggestions)."""
    wanted = " ".join(name.lower().split())
    names = {i.name.lower(): i for i in order.items}
    if wanted in names:
        return names[wanted], []
    partial = [i for n, i in names.items() if wanted and (wanted in n or n in wanted)]
    if len(partial) == 1:
        return partial[0], []
    close = difflib.get_close_matches(wanted, list(names), n=3, cutoff=0.6)
    if len(close) == 1:
        return names[close[0]], []
    suggestions = [i.name for i in partial] or [names[c].name for c in close] or [i.name for i in order.items]
    return None, suggestions


def item_refund(order: Order, items: list[tuple[str, int]], issue: str = "missing") -> dict:
    """Refund for missing, wrong, damaged or poor-quality items, as in refund policy section 5.1."""
    issue = (issue or "missing").lower().replace(" ", "_").replace("-", "_")
    if issue not in ISSUE_TYPES:
        issue = "missing"
    base = {
        "order_id": order.order_id,
        "issue": issue,
        "policy_source": "policies/refund-policy.md",
        "note": "This is an estimate. The customer raises the claim in the app: Help > select order.",
    }

    if order.status != "delivered" or order.delivered_minutes_ago is None:
        return base | {
            "eligible": False,
            "reason": f"The order isn't delivered yet (status: {STATUS_LABELS.get(order.status, order.status)}). "
            "Item problems can be reported after delivery.",
        }

    window = {
        "foreign_object": FOOD_SAFETY_WINDOW_MINUTES,
        "not_received": NOT_RECEIVED_WINDOW_MINUTES,
    }.get(issue, ITEM_ISSUE_WINDOW_MINUTES)
    if order.delivered_minutes_ago > window:
        hours = window // 60
        return base | {
            "eligible": False,
            "reason": f"It was delivered {order.delivered_minutes_ago / 60:.1f} hours ago. {issue.replace('_', ' ').capitalize()} "
            f"issues must be reported within {hours} hours of delivery. A team lead can approve an "
            "exception only in special circumstances.",
        }

    if order.item_total <= 0:
        return base | {"eligible": False, "reason": "This order has no priced items to refund."}

    whole_order = issue in ("foreign_object", "not_received")
    if issue == "not_received":
        return base | {
            "eligible": True,
            "refund_total": money(order.paid_upfront),
            "refund_to": _split_refund(order, order.paid_upfront),
            "reason": "'Marked delivered but not received' gets a full refund after verification "
            "(GPS trail, delivery PIN or photo, and a check with the delivery partner).",
            "needs_verification": True,
        }

    lines, unknown = [], []
    affected_value = Decimal(0)
    for raw_name, raw_qty in items or []:
        item, suggestions = match_item(order, str(raw_name))
        if item is None:
            unknown.append({"asked_for": raw_name, "items_in_this_order": suggestions})
            continue
        try:
            qty = int(raw_qty or 1)
        except (TypeError, ValueError):
            qty = 1
        capped = min(max(qty, 1), item.quantity)
        lines.append((item, capped, qty))
        affected_value += item.price * capped

    if unknown and not lines:
        return base | {
            "eligible": False,
            "reason": "None of those items are in this order.",
            "unknown_items": unknown,
            "order_items": [f"{i.quantity} × {i.name} (₹{money(i.price):.2f})" for i in order.items],
        }
    if not lines and not whole_order:
        return base | {"eligible": False, "reason": "Say which items (and how many) had the problem."}

    if whole_order or affected_value >= order.item_total:
        refund = order.paid_upfront
        result = base | {
            "eligible": True,
            "whole_order": True,
            "refund_total": money(refund),
            "refund_to": _split_refund(order, refund),
            "reason": "The whole order is affected, so the full amount paid is refunded, including fees and tip.",
        }
        if issue == "foreign_object":
            result["food_safety"] = (
                "Treated as a P1 food safety incident: the Food Safety team contacts the customer within "
                "24 hours, and the restaurant is investigated."
            )
        return result

    breakdown, total = [], Decimal(0)
    for item, qty, asked in lines:
        value = item.price * qty
        share = value / order.item_total
        packaging_share = order.packaging * share
        discount_share = order.coupon_discount * share
        pre_tax = value + packaging_share - discount_share
        gst = pre_tax * FOOD_GST
        refund_line = _r(pre_tax + gst)
        total += refund_line
        entry = {
            "item": f"{qty} × {item.name}",
            "item_value": money(value),
            "packaging_share": money(packaging_share),
            "discount_share": -money(discount_share),
            "gst_5pct": money(gst),
            "refund": money(refund_line),
        }
        if asked > item.quantity:
            entry["note"] = f"Only {item.quantity} were ordered, so the refund covers {item.quantity}."
        breakdown.append(entry)

    evidence = {
        "missing": "A photo of the bill and the items received, if asked (claims over ₹300 or frequent claims).",
        "wrong": "A photo of the wrong item.",
        "damaged": "A photo of the spill or damage.",
        "quality": "A photo and a short description.",
    }.get(issue, "A photo, if asked.")
    result = base | {
        "eligible": True,
        "whole_order": False,
        "reporting_window": f"Report within {window // 60} hours of delivery. This order was delivered "
        f"{order.delivered_minutes_ago:g} minutes ago, so it's still within the window.",
        "refund_total": money(total),
        "refund_to": _split_refund(order, total),
        "breakdown": breakdown,
        "how_it_is_calculated": "item price + its share of packaging − its share of the discount, plus 5% GST. "
        "Delivery, platform and other fees are refunded only when the whole order is refunded.",
        "evidence_needed": evidence,
        "refund_timeline": _timeline(order),
    }
    if issue in ("missing", "wrong") and order.delivered_minutes_ago <= REPLACEMENT_WINDOW_MINUTES:
        result["optional_replacement"] = (
            "Separate from the refund deadline: because it's under 45 minutes since delivery, the customer may "
            "also be offered 'Send the missing item' instead of a refund, if the restaurant is open and within 7 km."
        )
    if unknown:
        result["unknown_items"] = unknown
    return result


def on_time_promise(order: Order) -> dict | None:
    """Plus members get ₹50 CraveCart Money if an eligible order is more than 10 minutes late."""
    if not order.plus_member:
        return None
    if order.scheduled_slot_in_minutes is not None:
        return {"eligible": False, "reason": "Scheduled Orders aren't covered by the On-Time Promise."}
    late = order.minutes_late
    if late <= PLUS_ON_TIME_PROMISE_MINUTES:
        return {"eligible": False, "reason": f"{late:g} minutes late so far (needs more than 10)."}
    when = (
        "credited within 24 hours"
        if order.status == "delivered"
        else "credited within 24 hours of delivery (or cancel for free if it passes 30 minutes late)"
    )
    return {
        "eligible": True,
        "credit": money(PLUS_ON_TIME_CREDIT),
        "reason": f"{late:g} minutes past the promised time: ₹50 CraveCart Money {when}. "
        "Capped at 4 credits a month; not given if the customer cancels.",
    }
