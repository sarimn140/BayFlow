"""List envelopes (spec 03 §1.6, glossary §9).

Paginated collections return `Page[T]` = `{"items": [...], "total": n, "limit": l, "offset": o}`
with `?limit=` (default 20, 1-100) and `?offset=` (0 to `MAX_OFFSET`); the query behind it uses
a deterministic order and a `COUNT(*)` with the same filters (spec 01). Bounded lists (the
children of one booking, PO or configuration) return `ItemList[T]` = `{"items": [...]}` in full,
without pagination parameters. Every module uses these two classes, so OpenAPI has one schema per
item type (`Page_BookingSummary_`, `ItemList_QcInspectionRead_`, ...).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel, Field

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
# OFFSET is a bigint in PostgreSQL; an offset of 2**63 or more overflowed asyncpg's int64 encoder
# and became a 500 on every list. No list comes close to this bound; above it the answer is 422.
MAX_OFFSET = 2**31 - 1


@dataclass(frozen=True, slots=True)
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0


def get_page_params(
    limit: Annotated[
        int, Query(ge=1, le=MAX_LIMIT, description="Maximum number of items to return.")
    ] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET, description="Number of items to skip.")] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


PageParamsDep = Annotated[PageParams, Depends(get_page_params)]


class Page[T](BaseModel):
    """One page of a list response."""

    items: list[T]
    total: int = Field(ge=0, description="Number of items matching the filters, on all pages.")
    limit: int = Field(ge=1, le=MAX_LIMIT)
    offset: int = Field(ge=0, le=MAX_OFFSET)

    @classmethod
    def build(cls, items: Sequence[T], *, total: int, params: PageParams) -> "Page[T]":
        return cls(items=list(items), total=total, limit=params.limit, offset=params.offset)


class ItemList[T](BaseModel):
    """A bounded list (spec 03 §1.6, §3.1): `{items}` in full, without pagination."""

    items: list[T]
