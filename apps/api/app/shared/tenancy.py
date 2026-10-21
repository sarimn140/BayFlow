"""Tenant scoping (D20): the pieces a shop-scoped router needs, in one import.

D80 places the implementation in `app.shared.auth` (one file holds both dependency lookups,
spec 01 rule 8); this module re-exports it under the tenancy name. It imports `app.shared.auth`
only, never a module.
"""

from app.shared.auth import (
    SHOP_ROUTE_PREFIX,
    ShopContext,
    ShopContextDep,
    require_roles,
    require_shop_member,
    shop_scoped_router,
)

__all__ = [
    "SHOP_ROUTE_PREFIX",
    "ShopContext",
    "ShopContextDep",
    "require_roles",
    "require_shop_member",
    "shop_scoped_router",
]
