from __future__ import annotations

import pytest
import pyvips


@pytest.fixture
def photo_bytes() -> bytes:
    """A 1800×1200 landscape test photo with a gradient and some structure, as JPEG."""
    x = pyvips.Image.xyz(1800, 1200)
    r = (x[0] * 255 / 1800).cast("uchar")
    g = (x[1] * 255 / 1200).cast("uchar")
    b = ((x[0] + x[1]) % 255).cast("uchar")
    return r.bandjoin([g, b]).copy(interpretation="srgb").jpegsave_buffer(Q=92)
