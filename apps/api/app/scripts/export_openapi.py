"""Write the API's OpenAPI schema: `python -m app.scripts.export_openapi [output]` (D76, spec 07).

The default output is `<repo>/apps/web/src/lib/api/openapi.json` (its folder is created when
missing); `make gen-api` then generates the web client's types from it. The JSON is deterministic
(sorted keys, two-space indent, trailing newline, fixed `info.version`), so the committed file only
changes when the API contract does. Building the app performs no I/O, so no database is needed.
"""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.config import REPO_ROOT
from app.main import create_app

logger = logging.getLogger("app.scripts.export_openapi")

DEFAULT_OUTPUT = REPO_ROOT / "apps" / "web" / "src" / "lib" / "api" / "openapi.json"


def render_openapi() -> str:
    schema = create_app().openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.export_openapi",
        description="Write the BayFlow OpenAPI schema as deterministic JSON.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output file (default: {DEFAULT_OUTPUT})",
    )
    output: Path = parser.parse_args(argv).output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_openapi(), encoding="utf-8")
    logger.info("OpenAPI schema written to %s", output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
