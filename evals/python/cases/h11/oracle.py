"""Check malformed and valid chunk footers using in-memory messages."""

import h11

HEADERS = (
    b"POST /ordinary HTTP/1.1\r\nHost: example.invalid\r\n"
    b"Transfer-Encoding: chunked\r\n\r\n"
)


def events(connection: h11.Connection) -> list[object]:
    received = []
    for _ in range(10):
        event = connection.next_event()
        if event is h11.NEED_DATA or event is h11.PAUSED:
            return received
        received.append(event)
        if isinstance(event, h11.EndOfMessage):
            return received
    raise AssertionError("bounded event collection exhausted")


def test_security_regression() -> None:
    connection = h11.Connection(h11.SERVER)
    connection.receive_data(HEADERS + b"1\r\na__0\r\n\r\n")
    try:
        events(connection)
    except h11.RemoteProtocolError as error:
        assert "chunk footer" in str(error), (
            "SECURITY_REGRESSION: rejected for an unrelated reason"
        )
        return
    raise AssertionError("SECURITY_REGRESSION: malformed chunk terminator accepted")


def test_control_ordinary() -> None:
    connection = h11.Connection(h11.SERVER)
    connection.receive_data(HEADERS + b"1\r\na\r\n0\r\n\r\n")
    received = events(connection)
    assert (
        b"".join(event.data for event in received if isinstance(event, h11.Data))
        == b"a"
    )
    assert isinstance(received[-1], h11.EndOfMessage)


def test_control_boundary() -> None:
    connection = h11.Connection(h11.SERVER)
    connection.receive_data(HEADERS + b"1\r\na\r")
    first = events(connection)
    connection.receive_data(b"\n0\r\n\r\n")
    received = first + events(connection)
    assert (
        b"".join(event.data for event in received if isinstance(event, h11.Data))
        == b"a"
    )
    assert isinstance(received[-1], h11.EndOfMessage)
