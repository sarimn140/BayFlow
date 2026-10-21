"""Events the inventory module publishes (glossary §7.1, spec 01 event catalogue, D43).

A purchase-order receipt is the one inventory-led use case that involves a booking. Inventory never
imports bookings (spec 01 rule 3), so the receipt hands control to bookings through these two
events, which run synchronously in the receipt's transaction:

1. `PurchaseOrderReceiving` — only for a PO linked to a booking, before the PO or any part is
   locked: the bookings handler locks the booking first, so D30's lock order
   booking → purchase order → parts holds even though the use case started here.
2. `PurchaseOrderReceived` — after the `RECEIVE` movements, item quantities and PO status are
   written: while the linked booking is `PARTS_ORDERED`, bookings reserves the received stock
   (`inventory.service.reserve_received_for_booking`) and applies `RECEIVE_PARTS` when every
   booking part is fully reserved. With no subscriber the receipt still completes: the stock
   simply arrives as general stock.

**Their two `occurred_at` values differ on purpose (D63).** `PurchaseOrderReceiving` must run
before any lock, so its `occurred_at` is read before the locks and is informational only: no row
may ever be written with it. The receipt reads the clock once more, after its locks; every row the
receipt writes carries that instant, and `PurchaseOrderReceived.occurred_at` is exactly that
instant, so the handlers' writes (reservations, `RECEIVE_PARTS`) share it too.
"""

from dataclasses import dataclass
from uuid import UUID

from app.modules.inventory.domain.stock import PartQty
from app.shared.event_bus import Event


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseOrderReceiving(Event):
    """A receipt of a booking-linked PO is starting (nothing is locked by inventory yet).

    Subscribers lock the booking. `occurred_at` is read before any lock and is informational
    only: never write a row with it (use `PurchaseOrderReceived.occurred_at`).
    """

    shop_id: UUID
    purchase_order_id: UUID
    booking_id: UUID
    actor_user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseOrderReceived(Event):
    """A receipt was written. `occurred_at` is the receipt's single post-lock instant (D63): every
    row the receipt wrote carries it, and handlers write with it (`now=event.occurred_at`)."""

    shop_id: UUID
    purchase_order_id: UUID
    po_number: str
    booking_id: UUID | None
    received: tuple[PartQty, ...]
    actor_user_id: UUID
