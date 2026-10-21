"""The seed's data module against spec 11's rules, without a database (SEED-11 totals, SEED-17).

The time rules are checked for a seed run on each of the seven weekdays.
"""

from collections import Counter
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.scripts import seed_data as data
from app.scripts.seed import SHOP_TIMEZONE, calendar_for, run

MONDAY = date(2026, 10, 12)
SHOPS = {shop.slug: shop for shop in data.SHOPS}


def test_totals_match_spec_11() -> None:
    owners = {shop.owner.email for shop in data.SHOPS}
    staff = [member.email for shop in data.SHOPS for member in shop.staff]
    assert len(data.SHOPS) == 6
    assert len(owners) + len(set(staff)) + len(data.CUSTOMERS) == 36  # users
    assert len(staff) + len(data.SHOPS) == 32  # memberships, Fatima's two OWNER rows included
    assert sum(len(service.prices) for service in data.SERVICES) == 52
    assert len(data.PARTS) * len(data.SHOPS) == 96
    assert len(data.VEHICLES) == 10
    assert len(data.BOOKINGS) == 15
    events = sum(1 + sum(step.emits_event for step in script.steps) for script in data.BOOKINGS)
    assert events == 125


def test_every_shop_has_opening_stock_for_every_part() -> None:
    skus = {part.sku for part in data.PARTS}
    for shop in data.SHOPS:
        assert set(shop.opening_stock) == skus, shop.slug


def test_worked_example_parts_start_at_10_8_0_at_lahore_auto_care() -> None:
    lahore = SHOPS["lahore-auto-care"].opening_stock
    assert (lahore["FLT-OIL-01"], lahore["OIL-4L-01"], lahore["IGN-COIL-01"]) == (10, 8, 0)
    touched = {
        line["part_id"].sku
        for script in data.BOOKINGS
        if script.shop_slug == "lahore-auto-care"
        for step in script.steps
        for line in step.payload.get("lines", [])
        if line["line_type"] == "PART"
    }
    assert touched.isdisjoint({"FLT-OIL-01", "OIL-4L-01", "IGN-COIL-01"})


def _on_grid(shop: data.ShopSeed, slot: datetime) -> bool:
    local = slot.astimezone(SHOP_TIMEZONE)
    hours = shop.hours[local.weekday()]
    if hours is None:
        return False
    opens, closes = (time.fromisoformat(value) for value in hours)
    start = datetime.combine(local.date(), opens, tzinfo=SHOP_TIMEZONE)
    end = datetime.combine(local.date(), closes, tzinfo=SHOP_TIMEZONE)
    on_the_hour = (local - start) % timedelta(hours=1) == timedelta(0)
    return start <= local and local + timedelta(hours=1) <= end and on_the_hour


@pytest.mark.parametrize("weekday", range(7))
def test_scripts_keep_spec_11_time_rules_on_any_weekday(weekday: int) -> None:
    today = MONDAY + timedelta(days=weekday)
    start_of_today = datetime.combine(today, time(0), tzinfo=SHOP_TIMEZONE)
    calendars = {shop.slug: calendar_for(shop, today) for shop in data.SHOPS}
    slots: Counter[tuple[str, datetime]] = Counter()
    for script in data.BOOKINGS:
        calendar = calendars[script.shop_slug]
        shop = SHOPS[script.shop_slug]
        created = calendar.instant(script.created_at)
        steps = [calendar.instant(step.at) for step in script.steps]
        slot = calendar.instant(script.slot)
        label = f"{script.reference} on {today:%A}"
        times = [created, *steps]
        assert times == sorted(times), label
        assert len(set(times)) == len(times), label  # steps never share a minute
        assert all(instant < start_of_today for instant in times), label
        assert _on_grid(shop, slot), label
        assert created < slot <= created + timedelta(days=30), label
        if slot >= start_of_today and script.shop_slug == "lahore-auto-care":
            assert slot.astimezone(SHOP_TIMEZONE).hour != 10, label  # the worked example's slot
        slots[script.shop_slug, slot] += 1
    assert max(slots.values()) == 1  # every seeded slot keeps a free place (capacity 2)


def test_base_data_and_purchase_orders_come_before_the_sample_bookings() -> None:
    calendar = calendar_for(SHOPS["lahore-auto-care"], MONDAY)
    base = calendar.instant(data.at("B", "10:00"))
    first_booking = min(
        calendar_for(SHOPS[script.shop_slug], MONDAY).instant(script.created_at)
        for script in data.BOOKINGS
    )
    assert base < first_booking
    for order in data.PURCHASE_ORDERS:
        receipts = [calendar.instant(receipt.at) for receipt in order.receipts]
        assert all(calendar.instant(order.created_at) < moment for moment in receipts)
        assert max(receipts) < datetime.combine(MONDAY, time(0), tzinfo=SHOP_TIMEZONE)


def test_seed_is_skipped_unless_enabled_or_forced(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="app.seed")
    assert run(force=False) == 0  # the test environment sets SEED_ON_DEPLOY=false (SEED-09)
    assert "seed skipped (SEED_ON_DEPLOY is not true)" in caplog.text


def test_calendar_counts_open_days_only() -> None:
    lahore = calendar_for(SHOPS["lahore-auto-care"], date(2026, 10, 9))  # a Friday
    assert lahore.day("P1") == date(2026, 10, 8)
    assert lahore.day("P5") == date(2026, 10, 3)  # Sunday 4 Oct is closed
    assert lahore.day("F1") == date(2026, 10, 10)
    assert lahore.day("F2") == date(2026, 10, 12)  # Sunday 11 Oct is closed
    pindi = calendar_for(SHOPS["pindi-auto-garage"], date(2026, 10, 9))
    assert pindi.day("F2") == date(2026, 10, 11)  # Pindi opens on Sundays
    assert lahore.instant(data.at("F2", "10:00")) == datetime(2026, 10, 12, 5, 0, tzinfo=UTC)
