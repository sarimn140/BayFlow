"""Fixtures of the shops tests: builders hash each test password once (identity builders), and a
fake `ShopActivityReader` stands in for bookings' (D86) unless a test registers its own."""

from tests.modules.identity.builders import fast_password_hashing  # noqa: F401 - autouse fixture
from tests.modules.shops.fakes import (  # noqa: F401 - fixtures
    activity_reader,
    default_activity_reader,
)
