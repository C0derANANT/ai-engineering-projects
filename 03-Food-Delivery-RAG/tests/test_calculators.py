"""The money maths must match the worked examples in the policy documents exactly."""

import dataclasses

import pytest

from rag import calculators as calc


# ---- pricing (company/pricing-fees-and-membership.md) -----------------------------------
def test_pricing_document_worked_example():
    # Section 1: 5.2 km, rain fee ₹20, coupon ₹60, tip ₹20 -> ₹567.55
    result = calc.estimate_bill(480, 5.2, packaging=30, high_demand_fee=20, coupon_discount=60, tip=20)
    assert result["total"] == 567.55
    assert result["bill"]["delivery_fee"] == 37.6
    assert result["bill"]["gst_on_food_5pct"] == 22.5
    assert result["bill"]["gst_on_fees_18pct"] == 11.45


@pytest.mark.parametrize(
    "km, fee",
    [(0, 20), (2, 20), (3, 20), (3.05, 20.8), (4, 28), (5.2, 37.6), (7.5, 56), (9.8, 70), (10, 70)],
)
def test_delivery_fee_by_distance(km, fee):
    assert float(calc.delivery_fee(km)) == fee


@pytest.mark.parametrize("km", [10.1, 25, -1])
def test_delivery_fee_rejects_impossible_distances(km):
    with pytest.raises(calc.PolicyError):
        calc.delivery_fee(km)


def test_plus_free_delivery_and_high_demand_cap():
    result = calc.estimate_bill(450, 6.5, plus_member=True, high_demand_fee=40)
    assert result["bill"]["delivery_fee"] == 0
    assert result["bill"]["high_demand_fee"] == 20


def test_plus_free_delivery_needs_199_and_7km():
    assert calc.estimate_bill(150, 2, plus_member=True)["bill"]["delivery_fee"] == 20
    assert calc.estimate_bill(400, 8, plus_member=True)["bill"]["delivery_fee"] == 60


def test_small_cart_fee_below_149_only():
    assert calc.estimate_bill(148, 2)["bill"]["small_cart_fee"] == 25
    assert "small_cart_fee" not in calc.estimate_bill(149, 2)["bill"]


@pytest.mark.parametrize(
    "kwargs",
    [dict(item_total=0, distance_km=2), dict(item_total=100, distance_km=2, coupon_discount=150),
     dict(item_total=100, distance_km=2, tip=900), dict(item_total=100, distance_km=2, high_demand_fee=55)],
)
def test_estimate_bill_rejects_bad_input(kwargs):
    with pytest.raises(calc.PolicyError):
        calc.estimate_bill(**kwargs)


# ---- cancellation (policies/cancellation-policy.md) --------------------------------------
def test_stage_c_matches_policy_example_1(store):
    quote = calc.cancellation_quote(store.get("1042"))
    assert quote["stage"] == "C"
    assert quote["refund_total"] == 299.79
    assert quote["cancellation_fee"] == 253.83
    assert quote["coupon_restored"] is False
    assert quote["tip_refunded"] is True


def test_stage_c_keeps_delivery_fees_once_partner_is_at_restaurant(store):
    order = dataclasses.replace(store.get("1042"), partner_at_restaurant=True)
    assert calc.cancellation_quote(order)["refund_total"] == 266.75  # ₹28 delivery + ₹5.04 GST kept


def test_stage_d_refunds_nothing_without_tip(store):
    quote = calc.cancellation_quote(store.get("1043"))
    assert quote["stage"] == "D"
    assert quote["refund_total"] == 0


def test_stage_d_refunds_tip_only_before_pickup(store):
    preparing = dataclasses.replace(store.get("1042"), status="preparing")
    assert calc.cancellation_quote(preparing)["refund_total"] == 20  # policy example 2
    picked_up = dataclasses.replace(store.get("1042"), status="picked_up")
    assert calc.cancellation_quote(picked_up)["refund_total"] == 0


def test_grace_period_is_free_even_after_acceptance(store):
    order = store.get("1048")
    quote = calc.cancellation_quote(order)
    assert quote["stage"] == "free" and quote["refund_total"] == float(order.total)


def test_very_late_order_is_free_and_refunds_wallet_first(store):
    order = store.get("1044")
    quote = calc.cancellation_quote(order)
    assert quote["stage"] == "free" and "35" in quote["reason"]
    assert quote["refund_to"]["CraveCart Money"] == 100
    assert quote["refund_to"]["UPI"] == round(float(order.total) - 100, 2)


def test_no_partner_after_20_minutes_is_free(store):
    assert calc.cancellation_quote(store.get("1050"))["stage"] == "free"


def test_restaurant_not_accepted_is_free(store):
    assert "stage B" in calc.cancellation_quote(store.get("1051"))["reason"]


def test_scheduled_order_free_until_60_minutes_before_slot(store):
    order = store.get("1049")
    assert calc.cancellation_quote(order)["stage"] == "free"
    close = dataclasses.replace(order, scheduled_slot_in_minutes=45)
    assert calc.cancellation_quote(close)["stage"] == "C"


def test_cod_fee_becomes_outstanding_dues(store):
    order = store.get("1047")
    quote = calc.cancellation_quote(order)
    assert quote["refund_total"] == 0
    assert quote["outstanding_dues"] == float(order.total)
    assert quote["dues_note"]


@pytest.mark.parametrize("order_id", ["1045", "1046"])
def test_delivered_orders_cannot_be_cancelled(store, order_id):
    assert calc.cancellation_quote(store.get(order_id))["can_cancel"] is False


# ---- refunds (policies/refund-policy.md) -------------------------------------------------
def test_missing_item_matches_refund_policy_worked_example(store):
    result = calc.item_refund(store.get("1045"), [("Mutton Korma", 1)])
    assert result["refund_total"] == 283.5
    line = result["breakdown"][0]
    assert (line["packaging_share"], line["discount_share"], line["gst_5pct"]) == (15, -45, 13.5)
    assert "optional_replacement" in result  # delivered 25 minutes ago (< 45)


def test_item_names_are_matched_loosely(store):
    for name in ("mutton korma", "  MUTTON   KORMA ", "korma", "mutton kurma"):
        assert calc.item_refund(store.get("1045"), [(name, 1)])["refund_total"] == 283.5


def test_quantity_is_capped_at_what_was_ordered(store):
    result = calc.item_refund(store.get("1045"), [("Raita", 5)])
    assert "Only 1" in result["breakdown"][0]["note"]


def test_unknown_item_lists_the_real_items(store):
    result = calc.item_refund(store.get("1045"), [("Pizza", 1)])
    assert result["eligible"] is False
    assert any("Mutton Korma" in i for i in result["order_items"])


def test_every_item_missing_refunds_the_whole_order(store):
    order = store.get("1045")
    items = [(i.name, i.quantity) for i in order.items]
    result = calc.item_refund(order, items)
    assert result["whole_order"] and result["refund_total"] == float(order.total)


def test_foreign_object_is_full_refund_and_food_safety(store):
    result = calc.item_refund(store.get("1045"), [], "foreign_object")
    assert result["whole_order"] and "food_safety" in result


def test_report_window_has_closed_after_3_hours(store):
    result = calc.item_refund(store.get("1046"), [("Garlic Bread", 1)])
    assert result["eligible"] is False and "3 hours" in result["reason"]


def test_refund_needs_a_delivered_order(store):
    assert calc.item_refund(store.get("1042"), [("Dal Makhani", 1)])["eligible"] is False


def test_not_received_needs_verification(store):
    result = calc.item_refund(store.get("1045"), [], "not_received")
    assert result["needs_verification"] is True


def test_unknown_issue_type_falls_back_to_missing(store):
    assert calc.item_refund(store.get("1045"), [("Raita", 1)], "weird")["issue"] == "missing"


# ---- On-Time Promise ----------------------------------------------------------------------
def test_on_time_promise_for_late_plus_order(store):
    promise = calc.on_time_promise(store.get("1044"))
    assert promise["eligible"] and promise["credit"] == 50


def test_on_time_promise_only_for_plus(store):
    assert calc.on_time_promise(store.get("1042")) is None
