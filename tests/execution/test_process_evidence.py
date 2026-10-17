"""A process must remain bounded after it closes both output streams."""

import sys

from seam.execution.processes import run_process


def test_timeout_still_applies_after_child_closes_output_pipes() -> None:
    result = run_process(
        [
            sys.executable,
            "-c",
            "import os,time; os.close(1); os.close(2); time.sleep(.4)",
        ],
        timeout=0.05,
    )
    assert result.timed_out
    assert result.duration_seconds < 0.3
