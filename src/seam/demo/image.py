"""Build the trusted dependency image used by the synthetic demonstration."""

from pathlib import Path

from seam.constants import DEFAULT_IMAGE
from seam.demo.commands import execute_setup
from seam.demo.templates import write_template


def build_demo_image(
    directory: Path,
    *,
    docker: tuple[str, ...] = ("docker",),
    image: str = DEFAULT_IMAGE,
) -> None:
    """Build a trusted pytest environment before network-isolated verification."""
    context = directory / "container"
    context.mkdir()
    write_template(context / "Dockerfile", "Dockerfile.txt")
    execute_setup(
        [*docker, "build", "--tag", image, str(context)], directory, timeout=600
    )
