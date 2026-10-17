"""Read immutable demonstration templates bundled with the package."""

from importlib.resources import files
from pathlib import Path


def write_template(path: Path, name: str) -> None:
    """Copy one UTF-8 fixture template to its generated destination."""
    content = files("seam.demo").joinpath("resources", name).read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
