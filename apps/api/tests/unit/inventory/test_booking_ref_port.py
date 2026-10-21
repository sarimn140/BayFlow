"""The D86 `BookingRefReader` port of the inventory service (spec 01 rule 3, D89).

Inventory never imports bookings: bookings registers its reader at start-up. Without a reader, a
read that involves a booking must fail loud (`RuntimeError`), while reads without a booking id
never touch the port.
"""

from collections.abc import Collection, Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.modules.inventory import service as inventory_service
from app.shared.enums import BookingStatus


@dataclass(frozen=True)
class Ref:
    id: UUID
    reference: str
    status: BookingStatus
    version: int


@pytest.fixture
def restore_reader() -> Iterator[None]:
    previous = inventory_service.booking_ref_reader()
    yield
    inventory_service.register_booking_ref_reader(previous)


@pytest.mark.usefixtures("restore_reader")
async def test_an_unregistered_reader_fails_loud_once_a_booking_is_involved() -> None:
    inventory_service.register_booking_ref_reader(None)
    read = inventory_service._read_booking_refs
    assert await read(object(), shop_id=uuid4(), booking_ids=[]) == {}
    assert await read(object(), shop_id=uuid4(), booking_ids=[None]) == {}
    with pytest.raises(RuntimeError, match=r"register_ports\(\) must run first \(D86, D89\)"):
        await read(object(), shop_id=uuid4(), booking_ids=[uuid4()])


@pytest.mark.usefixtures("restore_reader")
async def test_a_registered_reader_gets_each_booking_once_on_the_callers_session() -> None:
    calls: list[tuple[Any, UUID, list[UUID]]] = []
    shop_id, first, second = uuid4(), uuid4(), uuid4()

    async def reader(
        session: Any, *, shop_id: UUID, booking_ids: Collection[UUID]
    ) -> dict[UUID, Ref]:
        calls.append((session, shop_id, list(booking_ids)))
        return {first: Ref(first, "BF-ABC123", BookingStatus.PARTS_ORDERED, 10)}

    inventory_service.register_booking_ref_reader(reader)
    assert inventory_service.booking_ref_reader() is reader
    session = object()
    refs = await inventory_service._read_booking_refs(
        session,
        shop_id=shop_id,
        booking_ids=[second, first, None, second],
    )
    assert calls == [(session, shop_id, sorted([first, second]))]
    assert refs[first].reference == "BF-ABC123"
    assert second not in refs
