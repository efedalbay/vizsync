import re
from collections.abc import Callable

import pytest

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def plain() -> Callable[[str], str]:
    """Remove colour codes, which CI adds even though the output is not a terminal."""
    return lambda output: _ANSI.sub("", output)
