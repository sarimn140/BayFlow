# Module: inventory

**Status:** Draft
**Package:** `app.modules.inventory`
**Owns tables:** `parts`, `stock_movements`, `booking_parts`, `purchase_orders`, `purchase_order_items` (glossary §7)
**Priority:** P0 (brief §7.6). The movement-history route and the multi-shop low-stock count are P1. Nothing is P2.

## Purpose

Own every number about parts: the per-shop catalogue, the stock ledger, the parts each booking needs, and purchase orders. Brief §7.6: "Per-shop parts catalog and quantity on hand · Required parts compared to stock automatically to show shortages · Purchase orders with items and statuses (ORDERED, PARTIALLY_RECEIVED, RECEIVED) · Receiving increases inventory; allocation decreases it and links parts to the booking; cancellation returns reserved parts." It also serves brief §7.4 (Parts Person: inventory table, jobs awaiting parts with required vs available, create POs, receive orders, allocate), §5.2 rows 8–10, §5.3 ("parts already in stock", "partial parts delivery", "cancellation … reserved parts must be released back to stock"), §6 steps 9–10, §2 "inventory chaos" and §3 "Wrong stock". Spec 00 narrative 3: every stock number is explainable, because it is a ledger.

This module never changes a booking's status. The bookings module runs the state machine (spec 08) and calls the functions below for the side effects of T12–T16 and T22, inside its own transaction. The PO receipt is the one inventory-led use case; it hands control to bookings through events (D43).

## In scope

- **P0**
  - Parts catalogue: list with `available`, `stock_state` and `on_order`; create, edit, deactivate (Owner and Parts Person, D44). New parts start at `on_hand = 0`.
  - Stock adjustments (`ADJUST`, Parts Person only): opening stock and count corrections (D82).
  - The ledger: every stock change writes exactly one `stock_movements` row per part with signed deltas (D42, D79).
  - Booking parts: create from the approved estimate (T12), reserve what is available and order the shortages (T13), reserve everything outstanding (T14), reserve received stock (T15), consume (T16), release on cancel (T22); labour-only jobs pass with zero rows (D31).
  - Shortage computation behind `BookingPartsRead` and `PartsSummary` (brief §7.6 "compared to stock automatically").
  - Purchase orders: general restock create (Parts Person), list and detail (Owner read-only, Parts Person), receipt by any Parts Person, partial receipts; booking-linked POs come only from `order-parts` (D43); `PO-XXXXXX` numbers.
  - Events `PurchaseOrderReceiving` and `PurchaseOrderReceived` (glossary §7.1).
  - Reads for other modules: live stock for the estimate editor (D40) and the inventory summary of the owner overview (brief §7.4 Owner).
- **P1:** `GET …/parts/{part_id}/movements` (ledger history); `count_low_stock` for the owner multi-shop summary; the CON-04 race test.
- **P2:** none (the bonus never touches stock).

## Out of scope

Supplier records (`supplier_name` is free text), price changes at receipt, cancelling, editing or closing a PO (the brief's three statuses only), returns to suppliers, automatic reordering, deleting parts (deactivate only, spec 02 §2), barcodes, several stock locations, any booking status change (bookings) and any notification (none of T13–T15 has a notification type; `PARTS_READY` on T16 belongs to notifications).

## Key decisions

| D | What it means here |
|---|---|
| D3 | One transaction per action: booking status, stock, PO and audit rows commit together (spec 01 ADR, worked-example step 10). |
| D16, D44, D66 | Catalogue (create/edit parts, SKU, cost, reorder level) = Owner + Parts Person (`parts.manage`). Stock operations (adjust, create PO, receive, reserve, allocate) = Parts Person only (`stock.manage`). The Owner reads stock, POs and the ledger. The web shows these buttons only from the membership's capabilities. |
| D20 | Every query and repository method takes `shop_id`; composite FKs make a cross-shop part, booking or PO reference impossible (SEC-45). |
| D21 | Booking-scoped stock data is read only through bookings routes, which apply the visibility predicate first; QC inspectors never see stock (403). |
| D24, D43 | Cancel releases reservations; open POs stay open. A receipt reserves for its linked booking **only while that booking is `PARTS_ORDERED`**; otherwise the stock stays general. |
| D30 | Lock order booking → purchase order → parts (ascending `id`) → slot counter; this module takes only the PO and part locks. |
| D31 | Zero `booking_parts` rows is a valid job: `mark-parts-ready` and `allocate-parts` pass, `order-parts` answers 409 `CONFLICT`. |
| D40 | The estimate editor shows live availability per part line (`PartStockRef`). |
| D41 | `unit_cost` is whole rupees (`Money`); `line_cost` and `total_cost` are integer products of whole rupees, so they need no rounding. |
| D42 | `parts.on_hand` / `parts.reserved` are cached ledger balances; `booking_parts` tracks `required_qty`, `reserved_qty`, `consumed_qty`. |
| D45 | `OUT` when available = 0, else `LOW` when available ≤ `reorder_level`, else `OK` (`StockState`). |
| D50 | Ids are generated in Python before flushing, so event metadata and PO numbers are known in the same transaction. |
| D63 | Nested functions receive the action's `now`; top-level use cases read `utcnow()` once, after their locks. All movements of one action share that instant. |
| D71 | Shared demo stock drifts as judges replay the worked example; it is corrected through the product (an `ADJUST` by the Parts Person), never by the seed. |
| D79 | `stock_movements.seq` breaks ties; history is ordered by `(created_at, seq)`. |
| D82 | `POST …/parts/{part_id}/adjustments` is **P0** (specs 03 and 10 agree); going below `reserved` or 0 → 409 `INSUFFICIENT_STOCK`. |
| D83 | A receipt that reserves stock for a booking without moving it must reach the booking's viewers as `booking.updated`: `reserve_received_for_booking` reports what it reserved, the bookings handler publishes `BookingPartsChanged` (glossary §7.1, `modules/bookings.md` §7.7) and notifications pushes (once the P1 WebSocket hub exists, D88; polling covers it before). |
| D86 | Inventory sits below bookings and never imports it. It declares the read port `BookingRefReader` and its registration function `inventory.service.register_booking_ref_reader()`; bookings implements it with `get_booking_refs` and registers it from its own `service.register_ports()` — the same pattern as shops' `ShopActivityReader` with `shops.service.register_activity_reader` (glossary §7.1a). |
| D89 | `router.py` exports `routers`; `app.main.wire_modules()` includes them and runs bookings' `register_ports()` at start-up, in tests and in the seed. Inventory has no `handlers.py` and never edits `app/main.py`. |

## Files

| File | Contents |
|---|---|
| `router.py` | One `shop_scoped_router(tags=["inventory"])` (D80) with the nine routes of spec 03 §4.10, exported as `routers` (D89). |
| `schemas.py` | Spec 03 §3.4–§3.5: `PartCreate`, `PartUpdate`, `PartRead`, `PartRef`, `PartStockRef`, `StockAdjustmentCreate`, `StockAdjustmentRead`, `StockMovementRead`, `BookingPartRead`, `BookingPartsRead`, `PartsSummary`, `PurchaseOrderCreate`, `PurchaseOrderReceive`, `PurchaseOrderSummary`, `PurchaseOrderRead`, `PurchaseOrderItemRead`, `PurchaseOrderRef`, `PurchaseOrderReceiveRead`, and `BookingRef` (only PO responses use it, so its one definition lives here). Internal: `StockSummary`. |
| `service.py` | Use cases and the functions other modules call (below); the `BookingRefReader` port and `register_booking_ref_reader()`. |
| `repository.py` | `PartRepository`, `BookingPartRepository`, `StockMovementRepository` (`add` and list only, append-only), `PurchaseOrderRepository`; lock helpers such as `lock_parts(*, shop_id, part_ids)` = `SELECT … WHERE shop_id = :shop_id AND id = ANY(:ids) ORDER BY id FOR UPDATE` (spec 02 §7.1). |
| `models.py` | Already implemented: `Part`, `BookingPart`, `PurchaseOrder`, `PurchaseOrderItem`, `StockMovement`. |
| `events.py` | `PurchaseOrderReceiving`, `PurchaseOrderReceived`. |
| `domain/stock.py` | `PartQty` value, stock maths and plans (pure, no I/O). |
| `domain/po_numbers.py` | `new_po_number(rng)`: `PO-` + 6 Crockford characters, never starting with `SEED`. |

No `handlers.py`: the module subscribes to nothing.

## Public service interface

Writes take the request's `UnitOfWork` (`uow`), reads an `AsyncSession` (`session`), always first (spec 01). Every function takes `shop_id` keyword-only (D20) — inside `ctx: ShopContext` for HTTP use cases. Top-level use cases commit; nested ones never commit. `PartQty` = `(part_id: UUID, qty: int)`, frozen.

**HTTP use cases (top-level; each commits once).** Routes gate roles with `require_roles`; the service re-asserts the D44 role and raises `Forbidden`, so the seed (which calls services directly as real actors, spec 11) cannot bypass it.

| Function | Returns | Raises |
|---|---|---|
| `list_parts(session, ctx, *, q, stock_states, include_inactive, sort, page)` | `Page[PartRead]` | — |
| `create_part(uow, ctx, data: PartCreate)` | `PartRead` (`on_hand = reserved = 0`) | 409 `CONFLICT` (SKU) |
| `update_part(uow, ctx, part_id, data: PartUpdate)` | `PartRead` | 404, 409 `CONFLICT` |
| `adjust_stock(uow, ctx, *, part_id, quantity_delta, reason)` | `StockAdjustmentRead` | 404, 409 `INSUFFICIENT_STOCK` |
| `list_part_movements(session, ctx, part_id, page)` *(P1)* | `Page[StockMovementRead]` | 404 |
| `list_purchase_orders(session, ctx, *, statuses, booking_id, page)` | `Page[PurchaseOrderSummary]` | — |
| `create_purchase_order(uow, ctx, data: PurchaseOrderCreate, *, po_number=None)` | `PurchaseOrderRead` | 422 |
| `get_purchase_order(session, ctx, po_id)` | `PurchaseOrderRead` | 404 |
| `find_purchase_order_id(session, *, shop_id, po_number)` (seed support) | `UUID \| None` — another shop's number → `None` | — |
| `receive_purchase_order(uow, ctx, po_id, data: PurchaseOrderReceive)` | `PurchaseOrderReceiveRead` | 404, 409 `CONFLICT`, 409 `CONCURRENT_UPDATE`, 422 |

`po_number=` is keyword-only and internal: only the seed passes it (`PO-SEED01`, `PO-SEED02`, spec 11); it is absent from every HTTP schema.

**Booking-action side effects (nested; called by `bookings.service` while it holds the booking lock; `now` = the action's instant).**

| Function | Rule | Returns (for event metadata, spec 08) | Raises |
|---|---|---|---|
| `create_booking_parts(uow, *, shop_id, booking_id, requirements: Sequence[PartQty], now)` | T12 | `None` | — |
| `order_missing_parts(uow, *, shop_id, booking_id, actor_user_id, items: Sequence[PartQty] \| None, supplier_name, now)` | T13 | `OrderPartsResult(purchase_order_id, po_number, reserved)` | 409 `CONFLICT`, 422 |
| `reserve_outstanding(uow, *, shop_id, booking_id, actor_user_id, now)` | T14 | `reserved: tuple[PartQty, …]` (recording it as metadata is optional; spec 08 lists none for T14) | 409 `INSUFFICIENT_STOCK` |
| `reserve_received_for_booking(uow, *, shop_id, booking_id, purchase_order_id, received: Sequence[PartQty], actor_user_id, now)` | T15 (bookings handler) | `ReceiptReservation(reserved: tuple[PartQty, …], all_reserved: bool)`: what this receipt reserved, and whether every `booking_parts` row is now fully reserved (bookings applies `RECEIVE_PARTS`, or publishes `BookingPartsChanged` when `reserved` is non-empty but not complete) | — |
| `consume_reservations(uow, *, shop_id, booking_id, actor_user_id, now)` | T16 | `consumed` | 409 `INSUFFICIENT_STOCK` |
| `release_reservations(uow, *, shop_id, booking_id, actor_user_id, now)` | T22 | `released` | — |

**Reads for other modules.**

| Function | Caller | Returns |
|---|---|---|
| `get_parts_for_estimate(session, *, shop_id, part_ids, include_stock=True)` | estimates (O1, T06, `EstimateLineRead.part`) | `dict[UUID, PartStockRef]`; unknown or other-shop ids are absent; `include_stock=False` nulls the stock fields (QC callers, spec 04 §B) |
| `get_booking_parts(session, *, shop_id, booking_id)` | bookings (`bookings_get_booking_parts`, after D21 and the QC 403) | `BookingPartsRead` |
| `get_booking_parts_summary(session, *, shop_id, booking_ids)` | bookings (`parts_summary` on lists and details; batch, API-11) | `dict[UUID, PartsSummary]`, one per id; zero rows → `{0, 0, 0, true}`. Bookings returns `null` before `assign-parts-person` and to QC callers |
| `get_stock_summary(session, *, shop_id)` | reporting | `StockSummary` (`parts_count`, `low_stock_count`, `out_of_stock_count`, `stock_value`, `open_purchase_orders`, `low_stock: list[PartRead]`) |
| `count_low_stock(session, *, shop_ids)` *(P1)* | reporting (owner summary) | `dict[UUID, int]` |

**The booking-reference port (D86).** `PurchaseOrderSummary.booking` is a `BookingRef` (`id`, `reference`, `status`, `version`) and `StockMovementRead.booking` needs the reference, but inventory may not import bookings (spec 01 rules 1, 3). Inventory therefore declares a read port, the same pattern as shops' `ShopActivityReader` with `shops.service.register_activity_reader` (`modules/shops.md` §5.3):

```python
# app/modules/inventory/service.py
class BookingRefData(Protocol):          # structural: any object with these attributes
    id: UUID; reference: str; status: BookingStatus; version: int

class BookingRefReader(Protocol):
    async def __call__(self, session: AsyncSession, *, shop_id: UUID,
                       booking_ids: Collection[UUID]) -> Mapping[UUID, BookingRefData]: ...

def register_booking_ref_reader(reader: BookingRefReader) -> None: ...   # called by bookings.service.register_ports() (D89)
```

Bookings' `service.register_ports()` registers `get_booking_refs` (`modules/bookings.md` §5.3), and `app.main.wire_modules()` runs it at start-up, in tests and in the seed (D89) — no import-time side effect (spec 01 rule 5). Until a reader is registered, a call raises `RuntimeError` (fail loud in a mis-wired test). Inventory maps the results to its own `BookingRef` schema, so the OpenAPI component is defined once. The reader runs on the caller's session, so after the receipt's handlers ran it sees the booking's new status and version.

## Endpoints

Served by this module (all `/api/v1/shops/{shop_id}/…`, member else 404; contracts in [spec 03 §4.10](../03-api-contracts.md) and §5.3):

| Method | Path | `operationId` | Roles | Success | Pri |
|---|---|---|---|---|---|
| GET | `…/parts` | `inventory_list_parts` | O, SA, T, PP (QC 403) | 200 `Page[PartRead]` | P0 |
| POST | `…/parts` | `inventory_create_part` | O, PP (`parts.manage`) | 201 `PartRead` | P0 |
| PATCH | `…/parts/{part_id}` | `inventory_update_part` | O, PP | 200 `PartRead` | P0 |
| POST | `…/parts/{part_id}/adjustments` | `inventory_adjust_stock` | PP (`stock.manage`) | 201 `StockAdjustmentRead` | **P0** (D82) |
| GET | `…/parts/{part_id}/movements` | `inventory_list_part_movements` | O, PP | 200 `Page[StockMovementRead]` | P1 |
| GET | `…/purchase-orders` | `inventory_list_purchase_orders` | O, PP | 200 `Page[PurchaseOrderSummary]` | P0 |
| POST | `…/purchase-orders` | `inventory_create_purchase_order` | PP | 201 `PurchaseOrderRead` | P0 |
| GET | `…/purchase-orders/{po_id}` | `inventory_get_purchase_order` | O, PP | 200 `PurchaseOrderRead` | P0 |
| POST | `…/purchase-orders/{po_id}/receive` | `inventory_receive_purchase_order` | PP (any active) | 200 `PurchaseOrderReceiveRead` | P0 |

Served by **bookings** with this module's data (spec 03 §4.8, §5.2): `GET …/bookings/{booking_id}/parts` (`bookings_get_booking_parts`, O/SA/T/PP + D21) → `get_booking_parts`; actions `assign-parts-person` → `create_booking_parts`, `order-parts` → `order_missing_parts`, `mark-parts-ready` → `reserve_outstanding`, `allocate-parts` → `consume_reservations`, `cancel` (both families) → `release_reservations`; the estimate editor and estimate reads → `get_parts_for_estimate`. Query parameters, sorts and bodies are exactly spec 03's (§4.10: `q`, repeatable `stock_state`, `include_inactive`, `sort` ∈ `sku`/`name`/`available` with optional `-`, default `sku`; PO `status` repeatable and `booking_id`).

## Domain rules and algorithms

### Quantities (never stored, spec 02 §6)

| Value | Definition |
|---|---|
| available | `on_hand − reserved` (≥ 0 by the CHECKs) |
| `stock_state` | `OUT` if available = 0; else `LOW` if available ≤ `reorder_level`; else `OK` (D45). SQL uses the same `CASE` for the `stock_state` filter |
| outstanding (per booking part) | `required_qty − reserved_qty − consumed_qty` |
| shortage | `max(0, outstanding − available)` |
| `on_order` (per part) | Σ `ordered_qty − received_qty` over items of the shop's `ORDERED` / `PARTIALLY_RECEIVED` POs |
| a booking part is "available" | outstanding = 0, or outstanding ≤ its part's available (used by `PartsSummary` and `BookingPartsRead`: `available_count`, `shortage_count = required_count − available_count`, `all_available = available_count == required_count`) |
| `line_cost`, `total_cost` | `ordered_qty × unit_cost`; Σ `line_cost` |

### Catalogue (D44)

- `sku` is trimmed and upper-cased by the schema, then must match `^[A-Z0-9][A-Z0-9._/-]{0,39}$`; unique per shop (`uq_parts_shop_id_sku` → 409 `CONFLICT`; another shop may reuse it, INV-17).
- `PartCreate` and `PartUpdate` have no stock fields (`extra="forbid"` → 422, SEC-17): every part is inserted with `on_hand = reserved = 0`, whoever creates it (INV-23). The first stock arrives by an `ADJUST` or a PO receipt by a Parts Person.
- Deactivating a part (`is_active = false`) hides it from new estimate lines (D40) and from new general POs; existing reservations, `booking_parts` rows, POs and estimate lines are untouched, and it can still be adjusted, reserved, ordered by `order-parts` (an approved estimate needs it) and received. Edits never rewrite estimate lines or PO items (they keep their own price and name).

### The ledger (D42, D79)

| `movement_type` | `quantity` | `on_hand_delta` | `reserved_delta` | `booking_id` | `purchase_order_id` | Written by |
|---|---|---|---|---|---|---|
| `RECEIVE` | q | +q | 0 | NULL | the PO | receipt |
| `RESERVE` | q | 0 | +q | the booking | the PO only for the reservation that follows a receipt | T13, T14, T15 |
| `RELEASE` | q | 0 | −q | the booking | NULL | T22 |
| `CONSUME` | q | −q | −q | the booking | NULL | T16 |
| `ADJUST` | \|d\| | d | 0 | NULL | NULL (`note` = reason, required) | adjustment |

These are exactly `ck_stock_movements_deltas` and `ck_stock_movements_links` (spec 02 §3.15). Each movement and its `parts` balance update are written together, under the part's row lock; `created_at` = the action's `now`; `actor_user_id` = the acting user (the customer on a customer cancel). Rows are never updated or deleted (repository has no update/delete; trigger `trg_stock_movements_append_only`). Invariants DI-1…DI-3 (spec 02 §6) hold after every function.

### Adjustment (D82)

Lock the part (`FOR UPDATE`, scoped by shop). `new_on_hand = on_hand + quantity_delta`. If `new_on_hand < reserved` (which includes `< 0`) → 409 `INSUFFICIENT_STOCK`, detail naming on hand, reserved and the lowest allowed delta `reserved − on_hand`; nothing changes (INV-25). Otherwise write one `ADJUST` movement and update `on_hand`. No booking is affected, so nothing is pushed.

### Booking parts (spec 08 T12–T16, T22; worked-example numbers in spec 08 "Parts reservations")

1. **T12 `create_booking_parts`.** Sum `requirements` per `part_id` (the approved version's `PART` lines, from `estimates.service.get_approved_part_requirements`) and insert one row per part: `required_qty` = sum, `reserved_qty = consumed_qty = 0`. No stock change, no part lock. Zero requirements → zero rows (D31). Runs once per booking (there is no way back to `ESTIMATE_APPROVED`); `uq_booking_parts_booking_id_part_id` is the backstop.
2. **T13 `order_missing_parts`.**
   1. Lock the booking's parts (ascending id). For each row compute outstanding and `reserve = min(available, outstanding)`; `shortage = outstanding − reserve`. Pure: `plan_order(rows, parts)`.
   2. No shortage anywhere (including zero rows) → 409 `CONFLICT` "All parts are available — use mark-parts-ready." Nothing is reserved or ordered (INV-03).
   3. `items` given → every short part must be listed (`items`, `missing_shortage`), only short parts may be listed (`items.N.part_id`, `not_short`), each with `qty ≥ shortage` (`items.N.quantity`, `below_shortage`); all violations are returned together as one 422 `VALIDATION_ERROR` (INV-04). `items` omitted → order exactly the shortages.
   4. Write the `RESERVE` movements (no PO id) and update `parts.reserved` and `booking_parts.reserved_qty`.
   5. Insert the PO (`ORDERED`, `booking_id` set, `supplier_name`, `created_by_user_id` = actor, new number) and one item per short part (`ordered_qty` = requested or shortage, `unit_cost = parts.unit_cost`). Return `{purchase_order_id, po_number, reserved}` for the `ORDER_PARTS` metadata.
3. **T14 `reserve_outstanding`.** Lock the parts; if any row's outstanding > its part's available → 409 `INSUFFICIENT_STOCK` naming the short parts, with nothing reserved (atomic, INV-10). Otherwise reserve every outstanding quantity. Zero rows pass trivially. Works from `PARTS_ORDERED` too (stock arrived another way, D43).
4. **T15 `reserve_received_for_booking`** (called only by the bookings handler, only when the locked booking is `PARTS_ORDERED`): for each received `(part_id, q)` with a `booking_parts` row, reserve `min(q, outstanding)` — `RESERVE` with the PO id; the excess stays general stock. The parts are already locked by the receipt. Return `ReceiptReservation(reserved, all_reserved)`: the `(part_id, qty)` reserved now, and whether every row of the booking has `reserved_qty + consumed_qty = required_qty`.
5. **T16 `consume_reservations`.** Lock the parts; any row with `reserved_qty ≠ required_qty` → 409 `INSUFFICIENT_STOCK` (INV-12). Otherwise one `CONSUME` of `required_qty` per row; `consumed_qty = required_qty`, `reserved_qty = 0` (satisfies `ck_booking_parts_consume_all`). Worked example ends at filter 9/0, oil 7/0, coil 0/0 (INV-11).
6. **T22 `release_reservations`.** Lock the parts of rows with `reserved_qty > 0`; one `RELEASE` per row; `reserved_qty = 0`. Called before bookings releases the slot (lock order). Linked POs are untouched; their later receipts become general stock (D24, INV-09). `DECLINE` (T03) needs no call: a `PENDING` booking has no rows.

### Purchase-order receipt (T15 trigger; spec 03 §5.3, spec 01 sequence diagram)

`receive_purchase_order(uow, ctx, po_id, data)` (`read_refs` below = the registered `BookingRefReader`):

1. Read the PO header (`booking_id`, `status`) unlocked, scoped by shop; missing → 404. `booking_id` never changes after insert, so reading it before the lock is safe.
2. If `booking_id` is set: `await uow.publish(PurchaseOrderReceiving(...))`; the bookings handler locks the booking first (D30, D43). Then read `before = read_refs(...)[booking_id]` as an immutable snapshot of `status` and `version` (never the reader's live object) (the booking is locked, so its status cannot change except through this transaction).
3. Lock the PO (`FOR UPDATE`, `populate_existing`). Read `now = utcnow()`.
4. Validate, in this order: PO already `RECEIVED` → 409 `CONFLICT`; an `item_id` not on this PO → 422 (`items.N.item_id`, `invalid_reference`); `expected_received_qty` given and ≠ the stored `received_qty` → 409 `CONCURRENT_UPDATE` (a duplicated receipt, INV-07); `quantity` > outstanding → 422 (`items.N.quantity`, `exceeds_outstanding`); every quantity 0 → 422 (`items`, `nothing_to_receive`).
5. Lock the parts with a quantity > 0 (ascending id). Per item: `RECEIVE` movement (+`on_hand`), `received_qty += q`.
6. PO status from its items (spec 02 §6): all complete → `RECEIVED` + `received_at = now`; otherwise `PARTIALLY_RECEIVED`.
7. `await uow.publish(PurchaseOrderReceived(..., received, occurred_at=now))`. Bookings: if the booking is `PARTS_ORDERED`, it calls `reserve_received_for_booking`; when `all_reserved` it applies `RECEIVE_PARTS` (event by this Parts Person, `actor_role` `PARTS_PERSON`, metadata `{purchase_order_id}`, its timestamps = `occurred_at`); when it reserved something without completing, it publishes `BookingPartsChanged` so notifications pushes `booking.updated` after commit (D83). Any other status (e.g. `CANCELLED`, or already `PARTS_READY`): nothing reserved, no event, no push (INV-24).
8. Build the response: `after = read_refs(...)`; `receive_parts_applied = before.status == PARTS_ORDERED and after.status == PARTS_READY`; `purchase_order.booking` = `after` as `BookingRef`. General POs: `booking` null, `receive_parts_applied` false.
9. `await uow.commit()`.

A partial delivery leaves the booking `PARTS_ORDERED` with the received units reserved for it (SM-12, INV-05); the final delivery fires `RECEIVE_PARTS` in the same transaction (INV-06). A general-restock PO only raises `on_hand` (INV-08).

### Purchase orders and numbers (D43)

- Statuses exactly `ORDERED` → `PARTIALLY_RECEIVED` → `RECEIVED`; no other transition exists, and nothing ever moves a PO back.
- General restock (`create_purchase_order`): `items` 1–50, distinct `part_id` (`duplicate`), each an **active** part of this shop (`items.N.part_id`, `invalid_reference`), `quantity` 1–10 000, `unit_cost` defaults to `parts.unit_cost`; `booking_id` in the body → 422 `extra_forbidden`. No locks (an insert).
- Numbers: `PO-` + 6 characters of the glossary §1 Crockford alphabet (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`), regenerated when they start with `SEED` (reserved for seed data, INV-20). The insert runs in `session.begin_nested()` and retries up to 5 times on `uq_purchase_orders_shop_id_po_number` (spec 02 §7.6). The seed's fixed `PO-SEED0n` values must match `ck_purchase_orders_po_number_format`.
- List order: open POs first, then newest: `ORDER BY (status = 'RECEIVED'), created_at DESC, id DESC`.

## Events

| Event | Published when | Payload (frozen dataclass, `occurred_at` from the base) | Subscribers |
|---|---|---|---|
| `PurchaseOrderReceiving` | Receipt step 2, only for a booking-linked PO, before the PO or any part is locked | `shop_id`, `purchase_order_id`, `booking_id`, `actor_user_id` (its `occurred_at` is read before the locks and is informational only: no row is written with it; every write uses the post-lock instant that `PurchaseOrderReceived.occurred_at` carries, D63) | bookings: lock the booking (D43) |
| `PurchaseOrderReceived` | Receipt step 7, after the `RECEIVE` movements, item quantities and PO status are written | `shop_id`, `purchase_order_id`, `po_number`, `booking_id` (nullable), `received: tuple[PartQty, …]`, `actor_user_id`; `occurred_at` = the receipt's `now` | bookings: reserve + `RECEIVE_PARTS` while `PARTS_ORDERED`, or `BookingPartsChanged` after a partial delivery (D83; notifications reacts to that event, not to this one) |

Subscribes to nothing. `BookingActionApplied` for the parts actions is published by bookings, not here.

## Permissions and visibility

| Capability (spec 04 RBAC B) | O | SA | T | PP | QC |
|---|---|---|---|---|---|
| List parts with stock | read | read (part picker) | read (part picker) | ✅ | 403 |
| Create / edit parts (`parts.manage`) | ✅ | 403 | 403 | ✅ | 403 |
| Adjust stock, create PO, receive PO (`stock.manage`) | 403 | 403 | 403 | ✅ (any active PP receives) | 403 |
| PO list / detail, movement ledger | read | 403 | 403 | ✅ | 403 |
| Booking parts (`…/bookings/{id}/parts`, via bookings) | all bookings | all bookings | assigned only (D21) | assigned only (D21) | 403 |
| `order-parts`, `mark-parts-ready`, `allocate-parts` (state machine) | 403 | 403 | 403 | assigned PP only | 403 |

Non-members get 404 on every route (router-level `require_shop_member`); a part, PO or item of another shop is 404 (or 422 `invalid_reference` inside a body). Stock fields are never shown to QC inspectors (`include_stock=False`).

## Errors

| Code | HTTP | When |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Schema failures; `invalid_reference` (part or item not in this shop/PO, inactive part on a general PO); `missing_shortage`, `below_shortage`, `not_short` (order-parts); `exceeds_outstanding`, `nothing_to_receive` (receipt); `duplicate`; `not_whole_rupees` |
| `FORBIDDEN` | 403 | Role outside the route's set (e.g. the Owner adjusting stock, a QC inspector listing parts) |
| `NOT_FOUND` | 404 | Unknown or other-shop part / PO; non-member |
| `CONFLICT` | 409 | Duplicate SKU; `order-parts` with nothing short; receiving a `RECEIVED` PO; `ck_purchase_order_items_quantities` backstop |
| `INSUFFICIENT_STOCK` | 409 | `mark-parts-ready` with a shortage; `allocate-parts` with incomplete reservations; an adjustment below `reserved` or 0; `ck_parts_*` / `ck_booking_parts_quantities` backstops |
| `CONCURRENT_UPDATE` | 409 | `expected_received_qty` mismatch; SQLSTATE `40P01` / `55P03` |

Booking-action errors (404 visibility, 403 role/assignment, 409 status and version) come from the state machine before these functions run (spec 03 §1.4).

## Concurrency and transactions

| Operation | Locks, in D30 order | Notes |
|---|---|---|
| T13, T14, T16, T22 | booking (bookings) → the booking's parts, ascending | T13's PO is an insert; T22 then the slot counter (bookings) |
| T12 | booking only | rows inserted |
| Receipt | booking (via `PurchaseOrderReceiving`) → PO → received parts, ascending | the PO lock serialises duplicate receipts |
| Adjustment, part edit | that part row | |
| Part create, general PO create, reads | none | |

- **Exactly one wins:** two bookings reserving the last unit (`mark-parts-ready` on both) serialise on the part row; the second sees available 0 and gets 409 `INSUFFICIENT_STOCK` (INV-19, lock-gate test). A receipt racing a cancel of its booking serialises on the booking row: either the receipt reserves and the cancel releases, or the cancel wins and nothing is reserved (CON-04). `cancel` racing `allocate-parts` serialises on the booking (CON-02).
- **No deadlocks:** every path takes at most one booking, then at most one PO, then parts in ascending id; adjustments take one part only.
- **Database backstops** (spec 02 §7.5): `ck_parts_reserved_lte_on_hand`, `ck_parts_*_non_negative`, `ck_booking_parts_quantities`, `ck_booking_parts_consume_all`, `ck_purchase_order_items_quantities`, `ck_stock_movements_*`, composite FKs; mapped by constraint name (spec 03 §2.4).
- Plans are computed first (pure domain) and applied second, so a 409/422 never leaves a half-applied plan; any later failure rolls the whole transaction back.

## Tests

- **Must pass (spec 12):** INV-01 ★ … INV-26 (INV-19 concurrency), SM-11 ★, SM-12 ★, SM-13, SM-18 steps 8–10, SEC-06, SEC-09, SEC-17 (stock fields), SEC-45 (`booking_parts` → other shop's part), EST-18 (live availability), API-11 (parts and PO lists, P1), CON-02, CON-04 (P1), SEED-04, SEED-12.
- **Proposed additions:**

| ID | Test |
|---|---|
| INV-27 | `order-parts` item validation returns `missing_shortage`, `not_short` and `below_shortage` together in one 422; nothing reserved |
| INV-28 | A receipt repeated with the same `expected_received_qty` → 409 `CONCURRENT_UPDATE` while the PO is still `PARTIALLY_RECEIVED`; stock unchanged |
| INV-29 | General PO with an inactive or other-shop part → 422 `invalid_reference`; a `booking_id` in the body → 422 `extra_forbidden` |
| INV-30 | Receipt rows: `RECEIVE` has `booking_id` NULL and the PO id; the following `RESERVE` carries both the booking and the PO id |
| INV-31 | `on_order` and `stock_state` on `GET …/parts`, and the `stock_state` filter (`OUT` wins over `LOW`, reorder level 0) |
| INV-32 | QC inspector: `GET …/parts` and `…/bookings/{id}/parts` → 403; estimate reads return `PartStockRef` with null stock fields |
| INV-33 | PO-number collision: an injected generator returns a taken number first; the PO is created with the next one |
| INV-34 | D83: a partial receipt reports its reservations (`ReceiptReservation.reserved`) and the booking's viewers get `booking.updated` (with bookings' `BookingPartsChanged` and notifications; = `modules/bookings.md` BK-33) |

## Implementation checklist

1. `domain/stock.py` and `domain/po_numbers.py` with unit tests (states, shortages, plans, PO status, number format, INV-15, INV-20, INV-26 checker).
2. `repository.py`: scoped getters, `lock_parts`, `get_po_for_update`, aggregates (`on_order`, item totals), append-only movement repository.
3. `schemas.py` (spec 03 §3.4–§3.5; `Money`, SKU normaliser, `extra="forbid"`).
4. Catalogue: `create_part`, `update_part`, `list_parts` + routes (needed by the seed in PH1, spec 14).
5. `adjust_stock` + route (P0, D82; the seed's opening stock).
6. Booking-action functions T12–T16, T22, called from the bookings executor (PH5).
7. General PO create, list, detail; `register_booking_ref_reader()` here, and bookings' `register_ports()` calling it with `get_booking_refs` (D89; `app/main.py` is not edited).
8. Receipt + `events.py`; the bookings handlers exist on the other side (spec 01 event catalogue).
9. `get_booking_parts`, `get_booking_parts_summary`, `get_parts_for_estimate`, `get_stock_summary`.
10. P1: movements route, `count_low_stock`.
11. Tests above; `assert_invariants` after every scenario.

## Dependencies (specs)

- [17-decisions.md](../17-decisions.md) D3, D16, D20, D21, D24, D30, D31, D40–D45, D50, D63, D71, D79, D82, D83, D86, D88, D89; [18-glossary.md](../18-glossary.md) §1, §5, §7, §9, §10.
- [08-booking-state-machine.md](../08-booking-state-machine.md) T12–T16, T22, "Parts reservations", metadata.
- [03-api-contracts.md](../03-api-contracts.md) §3.4, §3.5, §4.10, §5.2, §5.3; [02-data-model.md](../02-data-model.md) §3.13–§3.17, §6, §7, §8.
- [01-architecture.md](../01-architecture.md) layers, event catalogue, receipt sequence; [04-auth-and-security.md](../04-auth-and-security.md) RBAC B.
- [06-workflows.md](../06-workflows.md) P1–P8, E2, E3, E6, E7; [10-screens.md](../10-screens.md) PP-01…PP-05; [11-seed-data.md](../11-seed-data.md) inventory, POs; [12-quality-and-testing.md](../12-quality-and-testing.md) INV, CON.
- Other modules: [bookings.md](bookings.md) (`get_booking_refs`, the receipt handlers, `BookingPartsChanged`), estimates (`get_approved_part_requirements`), [identity.md](identity.md) (`get_users_by_ids` for `UserRef`), [shops.md](shops.md) (the same port pattern), [notifications.md](notifications.md) (D83 push), `reporting.md` (stock summary).

## Open questions

1. ✅ **Resolved by D86: booking-reference port.** `BookingRefReader` + `inventory.service.register_booking_ref_reader()`, implemented by `bookings.service.get_booking_refs` and registered through bookings' `register_ports()`, which `wire_modules()` calls (D89; glossary §7.1a; spec 01 describes the mechanism, its open question 10).
2. ✅ **Resolved by D82: adjustment priority.** Specs 03 (§4.1, §4.10) and 10 (E-46, PP-03) now mark adjustments P0.
3. ✅ **Resolved by D83, spec 03 §6.4 and spec 09 §2.7: the D83 push.** Clients treat a `booking.updated` with an **equal** version as a parts-state change and refetch the booking, its lists and the parts views; only an older version is ignored.
4. **POs that will never arrive.** There is no way to cancel or close a PO (brief statuses only). Its open quantity keeps counting in `on_order`. Acceptable for the hackathon?
5. ✅ **Resolved as built: `UserRef` home.** Actor names (`created_by`, `actor`) use spec 03's `UserRef`, defined once in `identity.schemas` (the lowest module; `modules/identity.md` §4 lists it, and estimates and qc already import it from there).

## Proposed glossary additions

| Kind | Name | Meaning |
|---|---|---|
| Wire enum (already proposed by spec 03) | `StockState` = `OK`, `LOW`, `OUT` | Computed (D45), never stored; kept in `app.shared.enums` next to `AiLegStatus` |
| Port | ✅ merged (glossary §7.1a, D86) — `BookingRefReader`, `inventory.service.register_booking_ref_reader()`; implementation `bookings.service.get_booking_refs` | Read port through which inventory gets `BookingRef` data without importing bookings |
| Return value | `ReceiptReservation` (`reserved`, `all_reserved`) | Result of `reserve_received_for_booking`, as `modules/bookings.md` §5.5 expects |
| Domain value | `PartQty` (`part_id`, `qty`) | Requirements, reservations, receipts, consumption and releases; `PurchaseOrderReceived.received` |
| Service functions | `get_booking_parts`, `get_booking_parts_summary` (batch signature), `count_low_stock`, `OrderPartsResult` | Refine spec 01's inventory surface |
| Field error code | (none new) | Uses spec 03 §2.3 codes only |
