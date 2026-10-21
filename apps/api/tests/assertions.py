"""Shared assertions (spec 12 §4.5).

- `assert_problem(response, status, code)`: an RFC 9457 problem body of spec 03 §2 that leaks no
  stack trace, SQL or exception class name.
- `assert_invariants(session)`: the database-wide invariants, checked after every scenario test and
  in SEED-06. Every check is a sum or a count, so the order of rows inside one action never
  matters (D79). Data built with `tests.rows` (no ledger, no events) is not expected to pass.
"""

import re
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PROBLEM_MEMBERS = ("type", "title", "status", "detail", "instance", "code")
PROBLEM_JSON = "application/problem+json"

_LEAKS = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r'File "[^"]+", line \d+'),
    re.compile(r"\b(?:sqlalchemy|asyncpg|psycopg|pydantic_core)\b", re.IGNORECASE),
    re.compile(r"\b(?:SELECT|INSERT INTO|UPDATE|DELETE FROM)\s"),
    re.compile(r"\b[A-Z][A-Za-z]*(?:Error|Exception)\b"),  # IntegrityError, KeyError, ...
)


def assert_problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    """Assert a problem+json response with `status` and glossary §10 `code`; return its body."""
    assert response.status_code == status, (response.status_code, response.text)
    assert response.headers.get("content-type") == PROBLEM_JSON, response.headers
    body: dict[str, Any] = response.json()
    missing = [member for member in PROBLEM_MEMBERS if member not in body]
    assert not missing, f"problem body lacks {missing}: {body}"
    assert body["status"] == status, body
    assert body["code"] == code, body
    for pattern in _LEAKS:
        assert not pattern.search(response.text), f"leaks internals ({pattern.pattern}): {body}"
    return body


# Each query returns the violating rows; an empty result means the invariant holds.
_CHECKS: tuple[tuple[str, str], ...] = (
    (
        "DI-1 part balance = sum of its movements",
        """
        SELECT p.sku, p.on_hand, p.reserved,
               COALESCE(SUM(m.on_hand_delta), 0) AS on_hand_sum,
               COALESCE(SUM(m.reserved_delta), 0) AS reserved_sum
        FROM parts p LEFT JOIN stock_movements m ON m.part_id = p.id
        GROUP BY p.id, p.sku, p.on_hand, p.reserved
        HAVING p.on_hand <> COALESCE(SUM(m.on_hand_delta), 0)
            OR p.reserved <> COALESCE(SUM(m.reserved_delta), 0)
        """,
    ),
    (
        "DI-2 part reserved = sum of booking_parts.reserved_qty",
        """
        SELECT p.sku, p.reserved, COALESCE(SUM(bp.reserved_qty), 0) AS held
        FROM parts p LEFT JOIN booking_parts bp ON bp.part_id = p.id
        GROUP BY p.id, p.sku, p.reserved
        HAVING p.reserved <> COALESCE(SUM(bp.reserved_qty), 0)
        """,
    ),
    (
        "INV-01 0 <= reserved <= on_hand",
        "SELECT sku, on_hand, reserved FROM parts WHERE reserved < 0 OR reserved > on_hand",
    ),
    (
        "DI-3 booking part quantities = its booking's movements",
        """
        SELECT bp.booking_id, bp.part_id, bp.reserved_qty, bp.consumed_qty,
               COALESCE(SUM(m.reserved_delta), 0) AS reserved_sum,
               COALESCE(SUM(m.quantity) FILTER (WHERE m.movement_type = 'CONSUME'), 0)
                   AS consumed_sum
        FROM booking_parts bp
        LEFT JOIN stock_movements m ON m.booking_id = bp.booking_id AND m.part_id = bp.part_id
        GROUP BY bp.id, bp.booking_id, bp.part_id, bp.reserved_qty, bp.consumed_qty
        HAVING bp.reserved_qty <> COALESCE(SUM(m.reserved_delta), 0)
            OR bp.consumed_qty
               <> COALESCE(SUM(m.quantity) FILTER (WHERE m.movement_type = 'CONSUME'), 0)
        """,
    ),
    (
        "DI-3 every booking movement belongs to a booking part",
        """
        SELECT m.booking_id, m.part_id, count(*) AS movements
        FROM stock_movements m
        WHERE m.booking_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM booking_parts bp
            WHERE bp.booking_id = m.booking_id AND bp.part_id = m.part_id)
        GROUP BY m.booking_id, m.part_id
        """,
    ),
    (
        "DI-4 slot counter = non-cancelled bookings of that slot",
        """
        WITH live AS (
            SELECT shop_id, slot_start, count(*) AS n
            FROM bookings WHERE status <> 'CANCELLED'
            GROUP BY shop_id, slot_start)
        SELECT COALESCE(c.shop_id, l.shop_id) AS shop_id,
               COALESCE(c.slot_start, l.slot_start) AS slot_start,
               c.booked_count, COALESCE(l.n, 0) AS live
        FROM slot_counters c
        FULL OUTER JOIN live l ON l.shop_id = c.shop_id AND l.slot_start = c.slot_start
        WHERE COALESCE(c.booked_count, 0) <> COALESCE(l.n, 0) OR c.booked_count < 0
        """,
    ),
    (
        "DI-5 cached estimate totals = sums of its lines",
        """
        SELECT e.id, e.version, e.parts_total, e.labour_total, e.grand_total
        FROM estimates e LEFT JOIN estimate_lines l ON l.estimate_id = e.id
        GROUP BY e.id, e.version, e.parts_total, e.labour_total, e.grand_total
        HAVING e.parts_total
               <> COALESCE(SUM(l.line_total) FILTER (WHERE l.line_type = 'PART'), 0)
            OR e.labour_total
               <> COALESCE(SUM(l.line_total) FILTER (WHERE l.line_type = 'LABOUR'), 0)
            OR e.grand_total <> e.parts_total + e.labour_total
        """,
    ),
    (
        "EST-16 at most one open estimate version per booking",
        """
        SELECT booking_id, count(*) AS open_versions FROM estimates
        WHERE status IN ('DRAFT', 'SUBMITTED', 'SENT')
        GROUP BY booking_id HAVING count(*) > 1
        """,
    ),
    (
        "EST-16 estimate versions are 1..n without gaps",
        """
        SELECT booking_id, min(version) AS first, max(version) AS last, count(*) AS versions
        FROM estimates GROUP BY booking_id
        HAVING min(version) <> 1 OR max(version) <> count(*)
        """,
    ),
    (
        "DI-6 purchase-order status matches its item quantities",
        """
        SELECT po.po_number, po.status, po.received_at IS NOT NULL AS has_received_at,
               bool_and(i.received_qty = 0) AS none_received,
               bool_and(i.received_qty = i.ordered_qty) AS all_received
        FROM purchase_orders po JOIN purchase_order_items i ON i.purchase_order_id = po.id
        GROUP BY po.id, po.po_number, po.status, po.received_at
        HAVING NOT (
            (po.status = 'ORDERED' AND bool_and(i.received_qty = 0))
            OR (po.status = 'PARTIALLY_RECEIVED' AND NOT bool_and(i.received_qty = 0)
                AND NOT bool_and(i.received_qty = i.ordered_qty))
            OR (po.status = 'RECEIVED' AND bool_and(i.received_qty = i.ordered_qty)))
            OR (po.received_at IS NOT NULL) <> (po.status = 'RECEIVED')
        """,
    ),
    (
        "DI-6 a purchase order has at least one item",
        """
        SELECT po.po_number FROM purchase_orders po
        WHERE NOT EXISTS (SELECT 1 FROM purchase_order_items i WHERE i.purchase_order_id = po.id)
        """,
    ),
    (
        "DI-7 the event chain starts with CREATE and links every status change",
        """
        WITH ordered AS (
            SELECT booking_id, action, from_status, to_status,
                   lag(to_status) OVER w AS previous_to,
                   row_number() OVER w AS n
            FROM booking_events
            WINDOW w AS (PARTITION BY booking_id ORDER BY created_at, seq))
        SELECT booking_id, n, action, from_status, to_status, previous_to FROM ordered
        WHERE (n = 1 AND (action <> 'CREATE' OR from_status IS NOT NULL
                          OR to_status <> 'PENDING'))
           OR (n > 1 AND (action = 'CREATE' OR from_status IS DISTINCT FROM previous_to))
        """,
    ),
    (
        "DI-7 latest event = booking status; version = number of events",
        """
        SELECT b.reference, b.status, b.version, count(e.id) AS events,
               (array_agg(e.to_status ORDER BY e.created_at DESC, e.seq DESC))[1] AS latest
        FROM bookings b LEFT JOIN booking_events e ON e.booking_id = b.id
        GROUP BY b.id, b.reference, b.status, b.version
        HAVING count(e.id) = 0
            OR (array_agg(e.to_status ORDER BY e.created_at DESC, e.seq DESC))[1] <> b.status
            OR b.version <> count(e.id)
        """,
    ),
)

_TENANCY = """
    SELECT n.id, n.type, n.recipient_user_id, n.booking_id
    FROM notifications n JOIN bookings b ON b.id = n.booking_id
    WHERE n.recipient_user_id <> b.customer_user_id
      AND NOT EXISTS (
          SELECT 1 FROM shop_memberships sm
          WHERE sm.shop_id = b.shop_id AND sm.user_id = n.recipient_user_id
            AND (sm.is_active OR :allow_inactive))
"""


async def invariant_violations(
    session: AsyncSession, *, allow_inactive_recipients: bool = False
) -> list[str]:
    """Every violated invariant with up to five offending rows (empty when all hold)."""
    problems: list[str] = []
    checks = [*_CHECKS, ("NOT-04 notification recipient is the customer or a member", _TENANCY)]
    for name, sql in checks:
        params = {"allow_inactive": allow_inactive_recipients} if sql is _TENANCY else {}
        rows = (await session.execute(text(sql), params)).mappings().all()
        if rows:
            sample = "; ".join(str(dict(row)) for row in rows[:5])
            problems.append(f"{name}: {len(rows)} violation(s): {sample}")
    return problems


async def assert_invariants(
    session: AsyncSession, *, allow_inactive_recipients: bool = False
) -> None:
    """Spec 12 §4.5.

    `allow_inactive_recipients` accepts a notification addressed to a member who was deactivated
    after it was written (NOT-04 holds at write time; the table keeps no history).
    """
    problems = await invariant_violations(
        session, allow_inactive_recipients=allow_inactive_recipients
    )
    assert not problems, "invariants violated:\n" + "\n".join(problems)
