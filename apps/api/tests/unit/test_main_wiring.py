"""Module wiring by convention (D89): `service.register_ports()`, `handlers.register(bus)` and
`router.routers` are loaded in the module-direction order, and absent files are skipped."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI

import app.main as main_module
from app.shared.event_bus import EventBus


def test_modules_are_listed_lowest_first_in_the_spec_01_direction() -> None:
    assert main_module.MODULES == (
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
        "audit",  # D97, spec 19 §6
        "admin",
        "calls",
    )


def test_wire_modules_registers_ports_then_handlers_then_routers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    router = APIRouter()

    @router.get("/api/v1/alpha-probe")
    async def alpha_probe() -> dict[str, str]:
        return {"ok": "yes"}

    def register_ports() -> None:
        calls.append("ports")

    def register(bus: EventBus) -> None:
        assert isinstance(bus, EventBus)
        calls.append("handlers")

    fake_modules = {
        "app.modules.alpha.service": SimpleNamespace(register_ports=register_ports),
        "app.modules.alpha.handlers": SimpleNamespace(register=register),
        "app.modules.alpha.router": SimpleNamespace(routers=(router,)),
    }
    monkeypatch.setattr(main_module, "_optional_module", fake_modules.get)

    app = FastAPI()
    main_module.wire_modules(app, EventBus(), modules=("alpha",))

    assert calls == ["ports", "handlers"]
    assert "/api/v1/alpha-probe" in app.openapi()["paths"]


def test_wire_modules_skips_modules_without_these_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "_optional_module", lambda _name: None)
    app = FastAPI()
    main_module.wire_modules(app, EventBus(), modules=("beta",))
    assert app.openapi()["paths"] == {}


def test_a_service_without_register_ports_is_fine(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_modules = {"app.modules.gamma.service": SimpleNamespace()}
    monkeypatch.setattr(main_module, "_optional_module", fake_modules.get)
    main_module.wire_modules(FastAPI(), EventBus(), modules=("gamma",))


def test_optional_module_returns_none_only_for_missing_files() -> None:
    assert main_module._optional_module("app.modules.identity.no_such_file") is None
    assert main_module._optional_module("app.modules.identity.service") is not None


def test_a_missing_package_counts_as_absent() -> None:
    """Spec 01 rule 6: deleting the bonus `app/modules/calls` package leaves the core working."""
    assert main_module._optional_module("app.modules.no_such_package.service") is None
    app = FastAPI()
    main_module.wire_modules(app, EventBus(), modules=("no_such_package",))
    assert app.openapi()["paths"] == {}


def test_import_errors_inside_an_existing_package_are_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "bf_broken_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("import bf_definitely_missing_dependency\n")
    (package / "service.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError) as caught:
        main_module._optional_module("bf_broken_pkg.service")
    assert caught.value.name == "bf_definitely_missing_dependency"
