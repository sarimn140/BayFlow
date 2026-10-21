"""The QC request field types inside a JSON body, through the app's real 422 handler.

Bookings builds `PassQcRequest` / `FailQcRequest` (spec 03 §5.2) from `QcChecklistWrite`,
`QcNotes`, `QcIssueTitle` and `QcIssueDescription`. A probe route with the same bodies proves the
field paths and codes spec 03 §2.3 promises: an unknown key is `enum` at `checklist.N.key` (QC-13),
a missing or blank issue field is 422 at `issue_title` / `issue_description` (QC-02), wrong types
and unknown fields are refused (SEC-17). The `checklist_incomplete` / `checklist_item_failed`
answers come from the service (`test_writes.py`), because only the service may judge a checklist
as a whole.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, ConfigDict

from app.modules.qc.schemas import QcChecklistWrite, QcIssueDescription, QcIssueTitle, QcNotes
from app.shared.enums import QcChecklistKey


class PassQcProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checklist: QcChecklistWrite
    notes: QcNotes = None
    expected_version: int | None = None


class FailQcProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_title: QcIssueTitle
    issue_description: QcIssueDescription
    checklist: QcChecklistWrite | None = None
    notes: QcNotes = None
    expected_version: int | None = None


probe = APIRouter(prefix="/api/v1/_qc_probe", tags=["test"])


@probe.post("/pass")
async def probe_pass(body: PassQcProbe) -> dict[str, Any]:
    return body.model_dump(mode="json")


@probe.post("/fail")
async def probe_fail(body: FailQcProbe) -> dict[str, Any]:
    return body.model_dump(mode="json")


@pytest.fixture
async def probe_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    app.include_router(probe)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


def items(**overrides: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": key.value, "passed": True, **overrides.get(key.value, {})} for key in QcChecklistKey
    ]


def field_errors(response: httpx.Response) -> list[tuple[str, str]]:
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    return [(error["field"], error["code"]) for error in body["errors"]]


async def test_a_valid_pass_body_is_parsed_trimmed_and_normalised(
    probe_client: httpx.AsyncClient,
) -> None:
    response = await probe_client.post(
        "/api/v1/_qc_probe/pass",
        json={"checklist": items(no_leaks={"note": "  dry  "}), "notes": "   "},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["checklist"][2] == {"key": "no_leaks", "passed": True, "note": "dry"}
    assert body["checklist"][0]["note"] is None
    assert body["notes"] is None


async def test_qc13_an_unknown_key_is_enum_at_checklist_n_key(
    probe_client: httpx.AsyncClient,
) -> None:
    body = items()
    body[3] = {"key": "brakes", "passed": True}
    response = await probe_client.post("/api/v1/_qc_probe/pass", json={"checklist": body})
    assert field_errors(response) == [("checklist.3.key", "enum")]
    message = response.json()["errors"][0]["message"]
    assert message == (
        "Input should be 'road_test', 'no_warning_lights', 'no_leaks', 'fluid_levels' "
        "or 'complaint_resolved'"
    )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"passed": "yes"}, ("checklist.1.passed", "bool_type")),
        ({"passed": 1}, ("checklist.1.passed", "bool_type")),
        ({"passed": None}, ("checklist.1.passed", "bool_type")),
        ({"note": "n" * 501}, ("checklist.1.note", "string_too_long")),
        ({"note": 5}, ("checklist.1.note", "string_type")),
        ({"label": "No warning lights"}, ("checklist.1.label", "extra_forbidden")),
    ],
    ids=["passed-yes", "passed-1", "passed-null", "note-501", "note-number", "label-sent"],
)
async def test_wrong_item_fields_are_422_at_their_path(
    probe_client: httpx.AsyncClient, change: dict[str, Any], expected: tuple[str, str]
) -> None:
    body = items(no_warning_lights=change)
    response = await probe_client.post("/api/v1/_qc_probe/pass", json={"checklist": body})
    assert field_errors(response) == [expected]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({}, [("checklist", "missing")]),
        ({"checklist": None}, [("checklist", "list_type")]),
        ({"checklist": "road_test"}, [("checklist", "list_type")]),
        ({"checklist": ["road_test"]}, [("checklist.0", "model_attributes_type")]),
        ({"checklist": items(), "notes": "n" * 2001}, [("notes", "string_too_long")]),
        ({"checklist": items(), "result": "PASS"}, [("result", "extra_forbidden")]),
        (
            {"checklist": [{"key": "road_test", "passed": True}] * 21},
            [("checklist", "too_long")],
        ),
    ],
    ids=[
        "no-checklist",
        "null",
        "a-string",
        "strings",
        "notes-2001",
        "mass-assignment",
        "21-items",
    ],
)
async def test_pass_body_shapes(
    probe_client: httpx.AsyncClient, payload: dict[str, Any], expected: list[tuple[str, str]]
) -> None:
    response = await probe_client.post("/api/v1/_qc_probe/pass", json=payload)
    assert field_errors(response) == expected


async def test_a_repeated_key_passes_the_schema_for_the_service_to_answer(
    probe_client: httpx.AsyncClient,
) -> None:
    """`checklist_incomplete` is the service's answer, so the schema must let the body through."""
    response = await probe_client.post(
        "/api/v1/_qc_probe/pass", json={"checklist": [*items(), items()[0]]}
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"issue_description": "Leak."}, [("issue_title", "missing")]),
        ({"issue_title": "Leak"}, [("issue_description", "missing")]),
        (
            {"issue_title": "  ", "issue_description": "Leak."},
            [("issue_title", "string_too_short")],
        ),
        (
            {"issue_title": "t" * 121, "issue_description": "x"},
            [("issue_title", "string_too_long")],
        ),
        (
            {"issue_title": "Leak", "issue_description": "d" * 2001},
            [("issue_description", "string_too_long")],
        ),
        (
            {"issue_title": "", "issue_description": ""},
            [("issue_title", "string_too_short"), ("issue_description", "string_too_short")],
        ),
        (
            {"issue_title": "Leak", "issue_description": "x", "checklist": [{"key": "x"}]},
            [("checklist.0.key", "enum"), ("checklist.0.passed", "missing")],
        ),
    ],
    ids=[
        "title-missing",
        "description-missing",
        "title-blank",
        "title-121",
        "description-2001",
        "both-empty",
        "bad-checklist",
    ],
)
async def test_qc02_fail_body_shapes(
    probe_client: httpx.AsyncClient, payload: dict[str, Any], expected: list[tuple[str, str]]
) -> None:
    response = await probe_client.post("/api/v1/_qc_probe/fail", json=payload)
    assert field_errors(response) == expected


async def test_a_fail_body_without_a_checklist_is_valid(probe_client: httpx.AsyncClient) -> None:
    response = await probe_client.post(
        "/api/v1/_qc_probe/fail",
        json={"issue_title": " Oil leak at filter ", "issue_description": "Seal weeping."},
    )
    assert response.status_code == 200
    assert response.json() == {
        "issue_title": "Oil leak at filter",
        "issue_description": "Seal weeping.",
        "checklist": None,
        "notes": None,
        "expected_version": None,
    }
