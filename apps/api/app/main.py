"""BayFlow API application factory (spec 01).

`create_app()` wires settings, logging, middleware, error handlers, event-bus subscriptions,
routers and the lifespan (engine created at start-up, disposed at shutdown). Nothing does I/O at
import time, so tests and the OpenAPI export can build the app without a database.
"""

import contextlib
import importlib
import importlib.util
import logging
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from enum import Enum
from types import ModuleType

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.error_handlers import install_problem_openapi, register_error_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.core.middleware import install_middleware
from app.core.security import limiter
from app.models_registry import MODEL_MODULES
from app.shared.event_bus import EventBus
from app.shared.uow import drain_after_commit_tasks

API_TITLE = "BayFlow API"
# A fixed string: the exported OpenAPI file changes only when the contract changes (spec 03 §1.1).
API_VERSION = "1.0.0"
API_DESCRIPTION = (
    "Multi-tenant auto repair shop platform. Errors are RFC 9457 `application/problem+json` "
    "with a `code` (glossary §10). Authenticate with the `bf_session` cookie or "
    "`Authorization: Bearer <access_token>`."
)

logger = logging.getLogger("app")


def operation_id(route: APIRoute) -> str:
    """spec 03 §1.11: operationId = `<tag>_<endpoint function name>` (`system_health`)."""
    if not route.tags:
        return route.name
    tag = route.tags[0]
    return f"{tag.value if isinstance(tag, Enum) else tag}_{route.name}"


# Every module in the module-direction order of spec 01, lowest first (D89). The order is the order
# in which read ports are registered, event handlers subscribed and routers included.
MODULES: tuple[str, ...] = (
    "identity",
    "shops",
    "scheduling",
    "ai",
    "inventory",
    "qc",
    "estimates",
    "bookings",
    "notifications",
    "reporting",
    "audit",
    "admin",
    "calls",
)


def _optional_module(name: str) -> ModuleType | None:
    """Import `name` if the file exists, else `None`.

    A missing parent package also counts as absent: `find_spec` imports the parents first, so
    without this a deleted bonus package (`app/modules/calls`, spec 01 rule 6) would crash
    `wire_modules()` with `ModuleNotFoundError`. Import errors inside an existing file, including
    a missing third-party dependency, are NOT swallowed.
    """
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError as exc:
        if exc.name is not None and name.startswith(f"{exc.name}."):
            return None
        raise
    if spec is None:
        return None
    return importlib.import_module(name)


def wire_modules(app: FastAPI, bus: EventBus, modules: Iterable[str] = MODULES) -> None:
    """Wire every module by convention (D89), so no module ever edits this file.

    For each module, in order:
    1. `service.register_ports()` if defined — registers read-port implementations into lower
       modules (D86), e.g. bookings → `shops.service.register_activity_reader(...)`;
    2. `handlers.register(bus)` if `handlers.py` exists — event subscriptions (spec 01);
    3. every `APIRouter` in `router.routers` if `router.py` exists.
    Nothing is subscribed or routed at import time; everything happens here, per app instance.
    """
    for module in modules:
        service = _optional_module(f"app.modules.{module}.service")
        register_ports = getattr(service, "register_ports", None)
        if callable(register_ports):
            register_ports()
        handlers = _optional_module(f"app.modules.{module}.handlers")
        if handlers is not None:
            handlers.register(bus)
        router_module = _optional_module(f"app.modules.{module}.router")
        if router_module is not None:
            routers: Iterable[APIRouter] = router_module.routers
            for router in routers:
                app.include_router(router)


def module_lifespans(
    modules: Iterable[str] = MODULES,
) -> list[Callable[[FastAPI], AbstractAsyncContextManager[None]]]:
    """D104: each module's `lifespan.lifespan(app)` if `lifespan.py` exists, in `MODULES` order."""
    hooks = []
    for module in modules:
        lifespan_module = _optional_module(f"app.modules.{module}.lifespan")
        if lifespan_module is not None:
            hooks.append(lifespan_module.lifespan)
    return hooks


def create_app(settings: Settings | None = None, *, database: Database | None = None) -> FastAPI:
    """Build the API. `database` lets tests inject an engine (e.g. with `NullPool`)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    for warning in settings.startup_warnings():
        logger.warning(warning)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = database or Database.from_settings(settings)
        app.state.db = db
        server_version = await db.server_version()
        logger.info(
            "BayFlow API %s starting (APP_ENV=%s, PostgreSQL %s, %d model modules)",
            API_VERSION,
            settings.app_env,
            server_version or "unreachable",
            len(MODEL_MODULES),
        )
        try:
            async with contextlib.AsyncExitStack() as stack:
                for hook in module_lifespans():  # D104: e.g. the calls sweeper
                    await stack.enter_async_context(hook(app))
                yield
        finally:
            await drain_after_commit_tasks()
            if database is None:
                await db.dispose()
            logger.info("BayFlow API stopped")

    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        redirect_slashes=False,  # a redirect through the Vercel rewrite would lose the cookie
        generate_unique_id_function=operation_id,
        lifespan=lifespan,
        debug=False,  # never render tracebacks
    )
    app.state.settings = settings
    app.state.event_bus = EventBus()
    app.state.limiter = limiter  # slowapi reads it from here
    register_error_handlers(app)
    install_middleware(app, settings)
    app.include_router(health_router)
    wire_modules(app, app.state.event_bus)
    install_problem_openapi(app)
    return app


app = create_app()
