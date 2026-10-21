"""Stand-ins for the two pinned bookings reads, used only while bookings has not landed them.

`bookings.service.get_booking_refs` and `list_booking_viewer_ids` are pinned interfaces that the
bookings module implements in parallel (wave 2); until then they raise `NotImplementedError`. The
`booking_reads` fixture probes them and, for each one that is still a stub, patches in the stand-in
below, which follows the documented contract (`modules/bookings.md` §5.3 and §7.11's pseudo-code):

- `get_booking_refs`: `BookingRefData` for each id that is a booking of `shop_id`;
- `list_booking_viewer_ids`: the customer, the shop's active SAs and Owner, its technician and
  parts person while active members, and the active QC inspectors while the booking is
  `QC_PENDING` / `QC_IN_PROGRESS` or when they inspected it. Unknown booking → `[]`.

The fixture's value says which implementation the test ran against ("real" or "fake").
"""

import uuid
from collections.abc import Awaitable, Collection

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.bookings import service as bookings_service
from app.modules.bookings.models import Booking
from app.modules.bookings.service import BookingRefData
from app.modules.qc import service as qc_service
from app.modules.shops import service as shops_service
from app.shared.enums import BookingStatus, MembershipRole

QC_QUEUE = frozenset({BookingStatus.QC_PENDING, BookingStatus.QC_IN_PROGRESS})


async def fake_get_booking_refs(
    session: AsyncSession, *, shop_id: uuid.UUID, booking_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, BookingRefData]:
    if not booking_ids:
        return {}
    statement = select(Booking.id, Booking.reference, Booking.status, Booking.version).where(
        Booking.shop_id == shop_id, Booking.id.in_(list(booking_ids))
    )
    rows = (await session.execute(statement)).all()
    return {
        row.id: BookingRefData(
            id=row.id,
            reference=row.reference,
            status=BookingStatus(row.status),
            version=row.version,
        )
        for row in rows
    }


async def fake_list_booking_viewer_ids(
    session: AsyncSession, *, booking_id: uuid.UUID
) -> list[uuid.UUID]:
    booking = await session.get(Booking, booking_id, populate_existing=True)
    if booking is None:
        return []
    shop_id = booking.shop_id
    active = set(
        await shops_service.list_active_member_ids(
            session, shop_id=shop_id, roles=list(MembershipRole)
        )
    )
    viewers = {booking.customer_user_id}
    viewers |= set(
        await shops_service.list_active_member_ids(
            session,
            shop_id=shop_id,
            roles=[MembershipRole.OWNER, MembershipRole.SERVICE_ADVISOR],
        )
    )
    viewers |= {booking.technician_user_id, booking.parts_person_user_id} & active
    qc_active = set(
        await shops_service.list_active_member_ids(
            session, shop_id=shop_id, roles=[MembershipRole.QC_INSPECTOR]
        )
    )
    if booking.status in QC_QUEUE:
        viewers |= qc_active
    viewers |= (
        set(await qc_service.list_inspector_ids(session, shop_id=shop_id, booking_id=booking_id))
        & qc_active
    )
    return sorted(viewers)


async def _is_stub(probe: Awaitable[object]) -> bool:
    try:
        await probe
    except NotImplementedError:
        return True
    return False


@pytest.fixture
async def booking_reads(db: Database, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Patch in the stand-ins for whichever pinned bookings read is still a stub."""
    used: dict[str, str] = {}
    async with db.sessionmaker() as session:
        if await _is_stub(
            bookings_service.get_booking_refs(session, shop_id=uuid.uuid4(), booking_ids=[])
        ):
            monkeypatch.setattr(bookings_service, "get_booking_refs", fake_get_booking_refs)
            used["get_booking_refs"] = "fake"
        else:
            used["get_booking_refs"] = "real"
        if await _is_stub(
            bookings_service.list_booking_viewer_ids(session, booking_id=uuid.uuid4())
        ):
            monkeypatch.setattr(
                bookings_service, "list_booking_viewer_ids", fake_list_booking_viewer_ids
            )
            used["list_booking_viewer_ids"] = "fake"
        else:
            used["list_booking_viewer_ids"] = "real"
    return used
