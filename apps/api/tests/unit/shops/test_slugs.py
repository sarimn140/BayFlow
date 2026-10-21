"""Shop slugs (D68, `modules/shops.md` §7.3; SHP-01 domain half)."""

import itertools
import re

import pytest

from app.modules.shops.domain.slugs import (
    FALLBACK_SLUG,
    SLUG_BASE_MAX_LENGTH,
    free_slug_candidates,
    slug_candidates,
    slugify,
)

SLUG_FORMAT = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")  # ck_shops_slug_format


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Lahore Auto Care", "lahore-auto-care"),
        ("  Raza   Auto -- Works!! ", "raza-auto-works"),
        ("Café Ñandú", "cafe-nandu"),
        ("Pindi Auto Garage (Rawalpindi)", "pindi-auto-garage-rawalpindi"),
        ("لاہور آٹو کیئر", FALLBACK_SLUG),  # an Urdu-only name
        ("!!!", FALLBACK_SLUG),
        ("A1 Motors 24/7", "a1-motors-24-7"),
        ("ＡＢＣ Motors", "abc-motors"),  # noqa: RUF001 - NFKD folds full-width letters
    ],
)
def test_shp01_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug
    assert SLUG_FORMAT.fullmatch(slug)


def test_shp01_long_names_are_cut_without_a_trailing_hyphen() -> None:
    slug = slugify("word " * 40)
    assert len(slug) <= SLUG_BASE_MAX_LENGTH
    assert SLUG_FORMAT.fullmatch(slug)
    cut = slugify("a" * 71 + " b")  # the cut lands right after a hyphen
    assert cut == "a" * 71


def test_shp01_candidates_count_from_two() -> None:
    assert list(itertools.islice(slug_candidates("shop"), 4)) == [
        "shop",
        "shop-2",
        "shop-3",
        "shop-4",
    ]


def test_shp01_free_candidates_skip_taken_slugs() -> None:
    taken = {"lahore-auto-care", "lahore-auto-care-2", "lahore-auto-care-4"}
    free = free_slug_candidates("lahore-auto-care", taken)
    assert list(itertools.islice(free, 3)) == [
        "lahore-auto-care-3",
        "lahore-auto-care-5",
        "lahore-auto-care-6",
    ]
