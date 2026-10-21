"""The shops and scheduling operations in the generated OpenAPI document (spec 03 §1.11, §4.1)."""

import httpx

EXPECTED = {
    ("GET", "/api/v1/me"): ("shops_get_me", "200", "shops"),
    ("GET", "/api/v1/public/shops"): ("shops_list_public_shops", "200", "shops"),
    ("GET", "/api/v1/public/cities"): ("shops_list_public_cities", "200", "shops"),
    ("GET", "/api/v1/public/shops/{shop_slug}"): ("shops_get_public_shop", "200", "shops"),
    ("POST", "/api/v1/shops"): ("shops_create_shop", "201", "shops"),
    ("GET", "/api/v1/shops/{shop_id}"): ("shops_get_shop", "200", "shops"),
    ("PATCH", "/api/v1/shops/{shop_id}"): ("shops_update_shop", "200", "shops"),
    ("PUT", "/api/v1/shops/{shop_id}/working-hours"): (
        "shops_replace_working_hours",
        "200",
        "shops",
    ),
    ("GET", "/api/v1/shops/{shop_id}/members"): ("shops_list_members", "200", "shops"),
    ("POST", "/api/v1/shops/{shop_id}/members"): ("shops_add_member", "201", "shops"),
    ("PATCH", "/api/v1/shops/{shop_id}/members/{membership_id}"): (
        "shops_update_member",
        "200",
        "shops",
    ),
    ("GET", "/api/v1/shops/{shop_id}/services"): ("shops_list_services", "200", "shops"),
    ("POST", "/api/v1/shops/{shop_id}/services"): ("shops_create_service", "201", "shops"),
    ("PATCH", "/api/v1/shops/{shop_id}/services/{service_id}"): (
        "shops_update_service",
        "200",
        "shops",
    ),
    ("GET", "/api/v1/public/shops/{shop_slug}/availability"): (
        "scheduling_get_availability",
        "200",
        "scheduling",
    ),
}


async def test_operation_ids_tags_and_success_statuses(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    found = {
        (method.upper(), path): operation
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
        if operation["tags"][0] in {"shops", "scheduling"}
    }
    assert set(found) == set(EXPECTED)
    for key, (operation_id, status, tag) in EXPECTED.items():
        operation = found[key]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == [tag]
        assert status in operation["responses"], key


async def test_wire_enums_and_list_envelopes(client: httpx.AsyncClient) -> None:
    components = (await client.get("/openapi.json")).json()["components"]["schemas"]
    assert components["Capability"]["enum"] == [
        "shop.manage",
        "team.manage",
        "services.manage",
        "parts.manage",
        "stock.manage",
        "tasks.manage",
    ]
    assert components["StaffRole"]["enum"] == [
        "SERVICE_ADVISOR",
        "TECHNICIAN",
        "PARTS_PERSON",
        "QC_INSPECTOR",
    ]
    assert set(components["ItemList_str_"]["properties"]) == {"items"}
    assert set(components["Page_ShopPublicSummary_"]["properties"]) == {
        "items",
        "total",
        "limit",
        "offset",
    }
    assert not [name for name in components if name.endswith(("-Input", "-Output"))]
    slot = components["SlotRead"]["properties"]
    assert set(slot) == {"slot_start", "slot_end", "remaining"}
    assert set(components["MeRead"]["properties"]) == {
        "id",
        "email",
        "full_name",
        "phone",
        "is_platform_admin",  # D94, spec 19 §4
        "memberships",
    }
