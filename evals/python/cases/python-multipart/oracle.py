"""Check Content-Length handling before consuming an in-memory stream."""

from io import BytesIO

from python_multipart.multipart import parse_form


def test_security_regression() -> None:
    stream = BytesIO(b"123456789012345")
    try:
        parse_form(
            {"Content-Type": b"application/octet-stream", "Content-Length": b"-1"},
            stream,
            lambda _: None,
            lambda _: None,
        )
    except ValueError as error:
        assert "Content-Length" in str(error), (
            "SECURITY_REGRESSION: rejected for unrelated reason"
        )
        assert stream.tell() == 0, (
            "SECURITY_REGRESSION: consumed body before rejecting header"
        )
        return
    raise AssertionError("SECURITY_REGRESSION: negative content length accepted")


def parse_size(headers: dict[str, bytes], body: bytes) -> int:
    files = []
    parse_form(headers, BytesIO(body), lambda _: None, files.append)
    return files[0].size


def test_control_ordinary() -> None:
    assert (
        parse_size(
            {"Content-Type": b"application/octet-stream", "Content-Length": b"10"},
            b"123456789012345",
        )
        == 10
    )


def test_control_boundary() -> None:
    assert parse_size({"Content-Type": b"application/octet-stream"}, b"12345") == 5
