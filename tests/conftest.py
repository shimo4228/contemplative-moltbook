"""Global pytest configuration.

Isolate tests from the real MOLTBOOK_HOME so test runs cannot write to
``~/.config/moltbook/``. This matters because several tests (notably
``test_agent.py::TestRunPostCycle::test_posts_dynamic``) mock the HTTP
client but exercise real ``memory.record_post()`` / ``episodes.append()``
code paths, which would otherwise leak mock content ("Reflective Note" /
"A short body about alignment.") into the live episode log. The 2026-04-12
weekly report flagged 17 such leaked records.

The env var MUST be set before any test module imports contemplative_agent,
because ``config.py`` captures MOLTBOOK_HOME at module load time into a
Path constant consumed by 14 modules. Setting it via an autouse fixture
would be too late.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_MOLTBOOK_TEST_HOME = Path(tempfile.mkdtemp(prefix="moltbook-pytest-"))
os.environ["MOLTBOOK_HOME"] = str(_MOLTBOOK_TEST_HOME)
