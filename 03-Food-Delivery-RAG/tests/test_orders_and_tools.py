import json

import pytest

from rag.orders import OrderStore, normalize_order_id
from rag.tools import build_tools


@pytest.mark.parametrize("raw", ["1042", "#1042", " 1042 ", "order 1042", "CC-1042", "Order #1042?"])
def test_order_ids_are_normalised(raw):
    assert normalize_order_id(raw) == "1042"


@pytest.mark.parametrize("raw", ["", None, "abc", "#12"])
def test_invalid_order_ids(raw):
    assert normalize_order_id(raw) is None


def test_unknown_order_lists_demo_ids(store):
    assert store.get("9999") is None
    message = store.not_found("9999")["error"]
    assert "#1042" in message and "#1052" in message


def test_summary_flags(store):
    late = store.summary(store.get("1044"))
    assert "free_cancellation" in late and late["plus_on_time_promise"]["eligible"]
    assert "delivery_pin" in store.summary(store.get("1049"))  # item total ₹1,000


def test_demo_table_has_every_order(store):
    assert len(store.table()) == len(store.ids()) == 11


def _write(tmp_path, orders):
    path = tmp_path / "orders.json"
    path.write_text(json.dumps({"orders": orders}), encoding="utf-8")
    return path


GOOD = {
    "order_id": "1", "items": [{"name": "Dosa", "price": 100, "quantity": 1}], "distance_km": 2,
    "delivery_fee": 20, "payment_method": "UPI", "status": "confirmed", "placed_minutes_ago": 2,
    "promised_minutes": 30,
}


@pytest.mark.parametrize(
    "change, message",
    [
        ({"order_id": "x"}, "order_id"),
        ({"status": "lost"}, "status"),
        ({"payment_method": "Bitcoin"}, "payment_method"),
        ({"items": []}, "at least one item"),
        ({"delivery_fee": 50}, "delivery_fee"),
    ],
)
def test_bad_order_data_is_rejected_clearly(tmp_path, change, message):
    order = {**GOOD, "order_id": "1001", **change}
    with pytest.raises(ValueError, match=message):
        OrderStore.from_file(_write(tmp_path, [order]))


def test_duplicate_ids_rejected(tmp_path):
    order = {**GOOD, "order_id": "1001"}
    with pytest.raises(ValueError, match="duplicate"):
        OrderStore.from_file(_write(tmp_path, [order, order]))


def test_missing_or_broken_orders_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        OrderStore.from_file(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="valid JSON"):
        OrderStore.from_file(bad)


# ---- tools --------------------------------------------------------------------------------
@pytest.fixture
def tools(store):
    return {t.name: t for t in build_tools(store)}


def test_tools_return_exact_numbers(tools):
    assert tools["cancellation_quote"].invoke({"order_id": "#1042"})["refund_total"] == 299.79
    refund = tools["item_refund_quote"].invoke(
        {"order_id": "1045", "items": [{"name": "mutton korma", "quantity": 1}], "issue": "missing"}
    )
    assert refund["refund_total"] == 283.5
    assert tools["estimate_bill"].invoke({"item_total": 480, "distance_km": 5.2, "packaging": 30,
                                          "high_demand_fee": 20, "coupon_discount": 60, "tip": 20})["total"] == 567.55


def test_tools_handle_unknown_orders_and_bad_input(tools):
    assert tools["lookup_order"].invoke({"order_id": "5555"})["found"] is False
    assert tools["cancellation_quote"].invoke({"order_id": "nope"})["found"] is False
    assert "error" in tools["estimate_bill"].invoke({"item_total": 300, "distance_km": 14})
