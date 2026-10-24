"""Bound one collection-merging performance component on a frozen Linux image."""

import multiprocessing
import resource
import signal

import pytest

from marshmallow import Schema, ValidationError, fields


class Record(Schema):
    number = fields.Integer(required=True)


def _load_invalid_records(connection):
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        signal.signal(signal.SIGXCPU, signal.SIG_DFL)
        resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
        try:
            Record().load([{"number": "ordinary-invalid"}] * 40_000, many=True)
        except ValidationError as error:
            expected = {"number": ["Not a valid integer."]}
            complete = len(error.messages) == 40_000 and all(
                error.messages.get(index) == expected for index in range(40_000)
            )
            connection.send(("complete", complete))
        else:
            connection.send(("complete", False))
    except Exception as error:
        connection.send(("error", type(error).__name__, str(error)))
    finally:
        connection.close()


def test_security():
    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_load_invalid_records, args=(sender,))
    try:
        process.start()
        sender.close()
        process.join(10)
        if process.is_alive():
            raise RuntimeError("Worker exceeded the wall deadline; result unresolved")
        assert process.exitcode != -signal.SIGXCPU, "BOUNDED_COLLECTION_MERGE_CPU"
        if process.exitcode != 0 or not receiver.poll():
            raise RuntimeError(f"Worker exited unexpectedly: {process.exitcode}")
        result = receiver.recv()
        if result[0] != "complete":
            raise RuntimeError(f"Worker could not run the check: {result!r}")
        assert result[1] is True, "BOUNDED_COLLECTION_MERGE_CPU"
    finally:
        if process.is_alive():
            process.terminate()
            process.join(2)
            if process.is_alive():
                process.kill()
                process.join()
        receiver.close()
        sender.close()
        process.close()


def test_valid_records():
    assert Record().load([{"number": "7"}, {"number": 11}], many=True) == [
        {"number": 7},
        {"number": 11},
    ]


def test_indexed_validation_messages():
    with pytest.raises(ValidationError) as error:
        Record().load([{"number": "ordinary-invalid"}, {}, {"number": 9}], many=True)
    assert error.value.messages == {
        0: {"number": ["Not a valid integer."]},
        1: {"number": ["Missing data for required field."]},
    }
