"""Prepare a public Jinja security backport case without importing target code."""

import argparse
import difflib
import json
import shlex
from pathlib import Path

from seam import repository
from seam.exceptions import RepositoryError

UPSTREAM = "https://github.com/pallets/jinja.git"
FIX = "7dd3680e6eea0d77fde024763657aa4d884ddb23"
TARGET = "2a48dd898d72f1a119ee923996e70aa43da04ea4"
FILTER_PATH = "src/jinja2/filters.py"
_OLD_BODY = """    rv = " ".join(
        f'{escape(key)}="{escape(value)}"'
        for key, value in d.items()
        if value is not None and not isinstance(value, Undefined)
    )
"""
_NEW_BODY = """    items = []

    for key, value in d.items():
        if value is None or isinstance(value, Undefined):
            continue

        if _space_re.search(key) is not None:
            raise ValueError(f"Spaces are not allowed in attributes: '{key}'")

        items.append(f'{escape(key)}="{escape(value)}"')

    rv = " ".join(items)
"""


def prepare(output: Path, source: Path | None, image: str, docker: str) -> None:
    """Clone exact public revisions and write an external oracle and reference diff."""
    command = tuple(shlex.split(docker))
    if not command or any("\x00" in item for item in command):
        raise ValueError("Docker command must contain ordinary arguments")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Output directory must be empty")
    repo = output / "repo"
    repository.git(
        output,
        "clone",
        "--no-local",
        "--no-hardlinks",
        "--no-checkout",
        "--no-recurse-submodules",
        "--",
        str(source.resolve()) if source is not None else UPSTREAM,
        str(repo),
    )
    if repository.resolve(repo, "3.0.3") != TARGET:
        raise ValueError(
            "Upstream tag 3.0.3 no longer identifies the expected revision"
        )
    repository.resolve(repo, FIX)
    repository.git(repo, "checkout", "--detach", TARGET)
    original = repository.git(repo, "show", f"{TARGET}:{FILTER_PATH}")
    heading = "@pass_eval_context\ndef do_xmlattr("
    if original.count(_OLD_BODY) != 1 or original.count(heading) != 1:
        raise ValueError("Target xmlattr implementation did not match the known case")
    adapted = original.replace(_OLD_BODY, _NEW_BODY).replace(
        heading, '_space_re = re.compile(r"\\s", flags=re.ASCII)\n\n\n' + heading
    )
    patch = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            adapted.splitlines(keepends=True),
            fromfile=f"a/{FILTER_PATH}",
            tofile=f"b/{FILTER_PATH}",
        )
    )
    repository.validate_patch(repo, patch)
    (output / "reference.patch").write_text(patch, "utf-8")
    example = Path(__file__).resolve().parent
    (output / "oracle.py").write_bytes((example / "oracle.py").read_bytes())
    config = (
        "schema_version = 1\nmax_attempts = 3\n\n"
        "[oracle]\n"
        'path = "oracle.py"\n'
        'security_test = "test_security_whitespace_attribute_keys"\n'
        'controls = ["test_control_valid_attributes_are_escaped", '
        '"test_control_none_and_undefined_are_omitted", '
        '"test_control_autospace_false_preserves_output"]\n'
        'failure_marker = "XMLATTR_WHITESPACE_SECURITY_REGRESSION"\n\n'
        "[runner]\n"
        f"image = {json.dumps(image)}\n"
        f"docker = {json.dumps(command)}\n"
        'suite = ["tests/test_filters.py"]\n'
        "timeout_seconds = 120\n"
    )
    (output / "harness.toml").write_text(config, "utf-8")
    (output / "source.json").write_text(
        json.dumps(
            {
                "repository": UPSTREAM,
                "fix_commit": FIX,
                "target_tag": "3.0.3",
                "target_commit": TARGET,
                "candidate": "manually adapted reference; no model used",
            },
            indent=2,
        )
        + "\n",
        "utf-8",
    )
    print(f"Prepared {output}")
    print("The source checkout is unchanged; reference.patch is supplied separately.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source", type=Path, help="Optional existing public Jinja clone"
    )
    parser.add_argument("--image", default="security-backport-jinja:local")
    parser.add_argument("--docker", default="docker")
    arguments = parser.parse_args()
    try:
        prepare(arguments.output, arguments.source, arguments.image, arguments.docker)
    except (OSError, ValueError, RepositoryError) as error:
        parser.exit(2, f"Preparation failed: {error}\n")


if __name__ == "__main__":
    main()
