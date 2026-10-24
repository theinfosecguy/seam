"""Check bounded multipart buffering without a timing threshold."""
from werkzeug.sansio.multipart import Data, Field, MultipartDecoder, NeedData, Preamble


def decoder_with_field():
    decoder = MultipartDecoder(b'ordinary-boundary')
    decoder.receive_data(
        b'--ordinary-boundary\r\nContent-Disposition: form-data; name="value"\r\n\r\n'
    )
    assert isinstance(decoder.next_event(), Preamble)
    assert isinstance(decoder.next_event(), Field)
    return decoder


def test_security():
    decoder = decoder_with_field()
    decoder.receive_data(b'x' * 128)
    event = decoder.next_event()
    assert isinstance(event, Data), 'MULTIPART_PENDING_DATA_RELEASED'
    assert event.data == b'x' * 128, 'MULTIPART_PENDING_DATA_RELEASED'
    assert len(decoder.buffer) == 0, 'MULTIPART_PENDING_DATA_RELEASED'


def test_complete_field():
    decoder = decoder_with_field()
    decoder.receive_data(b'ordinary\r\n--ordinary-boundary--\r\n')
    event = decoder.next_event()
    assert isinstance(event, Data)
    assert event.data == b'ordinary'
    assert event.more_data is False


def test_partial_boundary_waits():
    decoder = decoder_with_field()
    decoder.receive_data(b'\r\n--ordinary-boun')
    event = decoder.next_event()
    assert isinstance(event, Data)
    assert event.data == b''
    assert isinstance(decoder.next_event(), NeedData)
