"""Tools the LLM can call. Each wraps a calculator so money is always computed exactly."""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from . import calculators as calc
from .orders import OrderStore

# Shown in the chat while a tool runs
TOOL_STATUS = {
    "lookup_order": "Looking up the order",
    "cancellation_quote": "Working out the cancellation charges",
    "item_refund_quote": "Calculating the refund",
    "estimate_bill": "Pricing the bill",
}


class OrderIdArgs(BaseModel):
    order_id: str = Field(description="The order ID, for example '1042' or '#1042'.")


class ItemIssue(BaseModel):
    name: str = Field(description="Item name as the customer said it, for example 'mutton korma'.")
    quantity: int = Field(default=1, ge=1, description="How many units had the problem.")


class ItemRefundArgs(BaseModel):
    order_id: str = Field(description="The order ID, for example '1045'.")
    items: list[ItemIssue] = Field(
        default_factory=list,
        description="Affected items. Leave empty only for 'foreign_object' or 'not_received'.",
    )
    issue: Literal["missing", "wrong", "damaged", "quality", "foreign_object", "not_received"] = Field(
        default="missing", description="What went wrong."
    )


class BillArgs(BaseModel):
    item_total: float = Field(gt=0, description="Total price of the food items in ₹, before fees and discounts.")
    distance_km: float = Field(ge=0, description="Road distance from the restaurant in km.")
    packaging: float = Field(default=0, ge=0, description="Restaurant packaging charge in ₹.")
    plus_member: bool = Field(default=False, description="True if the customer has CraveCart Plus.")
    high_demand_fee: float = Field(default=0, ge=0, description="High-demand (rain/peak) fee in ₹, 0 if none.")
    late_night: bool = Field(default=False, description="True for orders placed 11:00 pm–5:59 am.")
    coupon_discount: float = Field(default=0, ge=0, description="Coupon discount in ₹.")
    tip: float = Field(default=0, ge=0, description="Tip for the delivery partner in ₹.")


def _field(item, name, default=None):
    return getattr(item, name, None) if not isinstance(item, dict) else item.get(name, default)


def build_tools(store: OrderStore) -> list[StructuredTool]:
    def lookup_order(order_id: str) -> dict:
        order = store.get(order_id)
        return store.summary(order) if order else store.not_found(order_id)

    def cancellation_quote(order_id: str) -> dict:
        order = store.get(order_id)
        return calc.cancellation_quote(order) if order else store.not_found(order_id)

    def item_refund_quote(order_id: str, items: list | None = None, issue: str = "missing") -> dict:
        order = store.get(order_id)
        if not order:
            return store.not_found(order_id)
        pairs = [(_field(i, "name", ""), _field(i, "quantity", 1) or 1) for i in (items or [])]
        return calc.item_refund(order, pairs, issue)

    def estimate_bill(**kwargs) -> dict:
        try:
            return calc.estimate_bill(**kwargs)
        except calc.PolicyError as exc:
            return {"error": str(exc)}

    return [
        StructuredTool.from_function(
            func=lookup_order,
            name="lookup_order",
            description="Get a demo order's status, items, bill, delivery timing, free-cancellation "
            "eligibility and CraveCart Plus On-Time Promise eligibility.",
            args_schema=OrderIdArgs,
        ),
        StructuredTool.from_function(
            func=cancellation_quote,
            name="cancellation_quote",
            description="Exact cancellation fee and refund if the customer cancelled a demo order now "
            "(stage, fee, refund split, outstanding COD dues, coupon and tip). Quote only; it does not cancel.",
            args_schema=OrderIdArgs,
        ),
        StructuredTool.from_function(
            func=item_refund_quote,
            name="item_refund_quote",
            description="Exact refund for missing, wrong, damaged or poor-quality items, a foreign object, "
            "or an order marked delivered but not received, on a delivered demo order. Checks the reporting window.",
            args_schema=ItemRefundArgs,
        ),
        StructuredTool.from_function(
            func=estimate_bill,
            name="estimate_bill",
            description="Price a hypothetical order line by line (delivery fee by distance, platform fee, "
            "small cart, high-demand and late-night fees, GST, Plus benefits) for 'how much would it cost' questions.",
            args_schema=BillArgs,
        ),
    ]
