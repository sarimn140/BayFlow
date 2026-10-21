"""Fixtures of the scheduling tests: builders hash each test password once, and a fake
`ShopActivityReader` (D86) serves the shops builders."""

from tests.modules.identity.builders import fast_password_hashing  # noqa: F401 - autouse fixture
from tests.modules.shops.fakes import default_activity_reader  # noqa: F401 - autouse fixture
