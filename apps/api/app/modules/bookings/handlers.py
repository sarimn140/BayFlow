"""Event subscriptions of the bookings module (`modules/bookings.md` §5.4; D37, D43, D83, D89).

Each handler runs synchronously inside the publisher's transaction (spec 01 "Event bus"): it never
commits, and an exception rolls the whole use case back.

- `PurchaseOrderReceiving` (inventory): lock the linked booking first, so a receipt keeps D30's
  lock order booking → purchase order → parts even though it started in inventory.
- `PurchaseOrderReceived` (inventory): reserve the received stock for a `PARTS_ORDERED` booking,
  then apply `RECEIVE_PARTS` or publish `BookingPartsChanged` (D43, D83).
- `ShopGridChanging` (shops): veto a slot-grid change while future bookings exist (D37).

`register(bus)` is called by `app.main.wire_modules()` at start-up (D89).
"""

from app.modules.bookings import service
from app.modules.inventory.events import PurchaseOrderReceived, PurchaseOrderReceiving
from app.modules.shops.events import ShopGridChanging
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork


async def on_purchase_order_receiving(event: PurchaseOrderReceiving, uow: UnitOfWork) -> None:
    """Lock 1 of a booking-linked receipt (§7.7 step 1). `occurred_at` is not used: the receipt's
    instant is the one carried by `PurchaseOrderReceived`."""
    await service.lock_booking_for_receipt(uow, shop_id=event.shop_id, booking_id=event.booking_id)


async def on_purchase_order_received(event: PurchaseOrderReceived, uow: UnitOfWork) -> None:
    """Reserve, then `RECEIVE_PARTS` or `BookingPartsChanged` (§7.7 step 2)."""
    await service.apply_purchase_order_receipt(uow, event)


async def on_shop_grid_changing(event: ShopGridChanging, uow: UnitOfWork) -> None:
    """409 `CONFLICT` while the shop has a booking after `occurred_at` that is not cancelled."""
    await service.veto_grid_change(uow.session, shop_id=event.shop_id, now=event.occurred_at)


def register(bus: EventBus) -> None:
    """Subscribe the three handlers (D89); nothing is subscribed at import time."""
    bus.subscribe(PurchaseOrderReceiving, on_purchase_order_receiving)
    bus.subscribe(PurchaseOrderReceived, on_purchase_order_received)
    bus.subscribe(ShopGridChanging, on_shop_grid_changing)
