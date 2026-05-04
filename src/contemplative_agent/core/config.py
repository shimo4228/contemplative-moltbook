"""Core security constants and content limits.

These constants are platform-independent and shared across all adapters.
"""

import re
from typing import Tuple

VALID_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
VALID_SUBMOLT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,49}$")

FORBIDDEN_SUBSTRING_PATTERNS: Tuple[str, ...] = (
    "api_key",
    "api-key",
    "apikey",
    "Bearer ",
    "auth_token",
    "access_token",
    "private_key",
    "-----BEGIN",
)
FORBIDDEN_WORD_PATTERNS: Tuple[str, ...] = (
    "password",
    "secret",
)

# Moltbook API char limits (verified via skill.md, 2026-05-04):
# - Post body: 40,000 chars
# - Post title: 300 chars
# - Comment / Reply: not specified (10,000 retained as conservative cap)
MAX_POST_LENGTH = 40000
MAX_POST_TITLE_LENGTH = 300
MAX_COMMENT_LENGTH = 10000
