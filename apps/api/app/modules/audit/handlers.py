"""Event subscriptions of the audit module (D89 `register(bus)`; spec 19 §3.2, §3.3; D95).

Every event of the catalogue becomes exactly one `audit_events` row, written by this module's
service **in the publisher's transaction**: the row commits with the change or not at all, and a
handler error rolls the change back (spec 01 "Event bus"). No handler commits, queues after-commit
work or does network I/O. `app.main.wire_modules()` subscribes these after the notifications
handlers (`MODULES` order, D97), so a booking action writes its notification rows first.

- identity: `LoginSucceeded`, `LoginFailed`, `LoginRateLimited`, `LoggedOut`, `OwnerRegistered`,
  `CustomerAccountCreated`, `UserActiveChanged`, `PlatformAdminChanged`;
- shops: `ShopCreated`, `ShopUpdated`, `WorkingHoursReplaced`, `ShopSuspensionChanged`,
  `MembershipAdded`, `MembershipRoleChanged`, `MembershipActiveChanged`;
- bookings: `BookingActionApplied` (one row per transition or operation, `CREATE` included).

The admin module's own entries (`admin.*`) are written by its service through this module's
service, because nothing below may publish them (spec 19 §3.3).
"""

from app.modules.audit import service
from app.modules.bookings.events import BookingActionApplied
from app.modules.identity.events import (
    CustomerAccountCreated,
    LoggedOut,
    LoginFailed,
    LoginRateLimited,
    LoginSucceeded,
    OwnerRegistered,
    PlatformAdminChanged,
    UserActiveChanged,
)
from app.modules.shops.events import (
    MembershipActiveChanged,
    MembershipAdded,
    MembershipRoleChanged,
    ShopCreated,
    ShopSuspensionChanged,
    ShopUpdated,
    WorkingHoursReplaced,
)
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork


async def on_login_succeeded(event: LoginSucceeded, uow: UnitOfWork) -> None:
    await service.record_login_succeeded(uow, event)


async def on_login_failed(event: LoginFailed, uow: UnitOfWork) -> None:
    await service.record_login_failed(uow, event)


async def on_login_rate_limited(event: LoginRateLimited, uow: UnitOfWork) -> None:
    await service.record_login_rate_limited(uow, event)


async def on_logged_out(event: LoggedOut, uow: UnitOfWork) -> None:
    await service.record_logged_out(uow, event)


async def on_owner_registered(event: OwnerRegistered, uow: UnitOfWork) -> None:
    await service.record_owner_registered(uow, event)


async def on_customer_account_created(event: CustomerAccountCreated, uow: UnitOfWork) -> None:
    await service.record_customer_created(uow, event)


async def on_user_active_changed(event: UserActiveChanged, uow: UnitOfWork) -> None:
    await service.record_user_active_changed(uow, event)


async def on_platform_admin_changed(event: PlatformAdminChanged, uow: UnitOfWork) -> None:
    await service.record_platform_admin_changed(uow, event)


async def on_shop_created(event: ShopCreated, uow: UnitOfWork) -> None:
    await service.record_shop_created(uow, event)


async def on_shop_updated(event: ShopUpdated, uow: UnitOfWork) -> None:
    await service.record_shop_updated(uow, event)


async def on_working_hours_replaced(event: WorkingHoursReplaced, uow: UnitOfWork) -> None:
    await service.record_working_hours_replaced(uow, event)


async def on_shop_suspension_changed(event: ShopSuspensionChanged, uow: UnitOfWork) -> None:
    await service.record_shop_suspension_changed(uow, event)


async def on_membership_added(event: MembershipAdded, uow: UnitOfWork) -> None:
    await service.record_membership_added(uow, event)


async def on_membership_role_changed(event: MembershipRoleChanged, uow: UnitOfWork) -> None:
    await service.record_membership_role_changed(uow, event)


async def on_membership_active_changed(event: MembershipActiveChanged, uow: UnitOfWork) -> None:
    await service.record_membership_active_changed(uow, event)


async def on_booking_action_applied(event: BookingActionApplied, uow: UnitOfWork) -> None:
    await service.record_booking_action(uow, event)


def register(bus: EventBus) -> None:
    """Subscribe every catalogue event (D89); nothing is subscribed at import time."""
    bus.subscribe(LoginSucceeded, on_login_succeeded)
    bus.subscribe(LoginFailed, on_login_failed)
    bus.subscribe(LoginRateLimited, on_login_rate_limited)
    bus.subscribe(LoggedOut, on_logged_out)
    bus.subscribe(OwnerRegistered, on_owner_registered)
    bus.subscribe(CustomerAccountCreated, on_customer_account_created)
    bus.subscribe(UserActiveChanged, on_user_active_changed)
    bus.subscribe(PlatformAdminChanged, on_platform_admin_changed)
    bus.subscribe(ShopCreated, on_shop_created)
    bus.subscribe(ShopUpdated, on_shop_updated)
    bus.subscribe(WorkingHoursReplaced, on_working_hours_replaced)
    bus.subscribe(ShopSuspensionChanged, on_shop_suspension_changed)
    bus.subscribe(MembershipAdded, on_membership_added)
    bus.subscribe(MembershipRoleChanged, on_membership_role_changed)
    bus.subscribe(MembershipActiveChanged, on_membership_active_changed)
    bus.subscribe(BookingActionApplied, on_booking_action_applied)
