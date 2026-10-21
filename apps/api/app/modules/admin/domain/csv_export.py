"""The audit export's CSV rules (spec 19 §4 E-75, §7). Pure.

- RFC 4180: comma-separated, CRLF line ends, a field holding a comma, a double quote or a line
  break is wrapped in double quotes and its double quotes are doubled (Python's `csv` module with
  the `excel` dialect and `\\r\\n` endings does exactly this); the first line is the header.
- Formula injection (OWASP "CSV Injection"): a cell starting with `=`, `+`, `-` or `@` — and, as
  OWASP also lists, a tab or a carriage return — is prefixed with `'`, so a spreadsheet shows it as
  text instead of evaluating it. The header row is fixed text and never needs it.
"""

import csv
import io
from collections.abc import Iterable, Iterator, Sequence
from typing import Final

FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r")
LINE_END: Final = "\r\n"


def neutralise(cell: str) -> str:
    """`cell` with a leading `'` when a spreadsheet would read it as a formula."""
    return f"'{cell}" if cell.startswith(FORMULA_PREFIXES) else cell


def csv_line(cells: Sequence[str], *, neutralised: bool = True) -> str:
    """One RFC 4180 record, ending in CRLF."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=LINE_END)
    writer.writerow([neutralise(cell) for cell in cells] if neutralised else list(cells))
    return buffer.getvalue()


def csv_lines(header: Sequence[str], rows: Iterable[Sequence[str]]) -> Iterator[str]:
    """The header line, then one line per row."""
    yield csv_line(header, neutralised=False)
    for row in rows:
        yield csv_line(row)
