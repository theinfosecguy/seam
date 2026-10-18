"""Bound source snapshots and validate immutable container images."""

import re
from typing import Final

MAX_SNAPSHOT_BYTES: Final = 256 * 1_048_576

MAX_SNAPSHOT_FILES: Final = 20_000

MAX_SNAPSHOT_DEPTH: Final = 100

MAX_SNAPSHOT_LINKS: Final = 40

MAX_SNAPSHOT_PATH_CHARACTERS: Final = 1024

IMAGE_ID_PATTERN: Final = re.compile(r"sha256:[a-f0-9]{64}")
