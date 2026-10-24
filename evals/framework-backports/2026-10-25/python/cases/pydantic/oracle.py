"""Check finite completion and ordinary date parsing without an unbounded loop."""

import multiprocessing
import resource
import signal
from datetime import date, datetime, timezone

from pydantic.datetime_parse import parse_date, parse_datetime


def _parse_extreme_dates(connection):
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        signal.signal(signal.SIGXCPU, signal.SIG_DFL)
        resource.setrlimit(resource.RLIMIT_CPU, (1, 2))
        results = [
            parse_date("infinity"),
            parse_date("-infinity"),
            parse_date(float("inf")),
            parse_datetime("infinity"),
            parse_datetime("-infinity"),
            parse_datetime(float("-inf")),
        ]
        connection.send(("complete", results))
    except Exception as error:
        connection.send(("error", type(error).__name__, str(error)))
    finally:
        connection.close()


def test_security():
    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_parse_extreme_dates, args=(sender,))
    try:
        process.start()
        sender.close()
        process.join(10)
        if process.is_alive():
            raise RuntimeError("Worker exceeded the wall deadline; result unresolved")
        assert process.exitcode != -signal.SIGXCPU, "EXTREME_DATE_PARSING_COMPLETES"
        if process.exitcode != 0 or not receiver.poll():
            raise RuntimeError(f"Worker exited unexpectedly: {process.exitcode}")
        result = receiver.recv()
        if result[0] != "complete":
            raise RuntimeError(f"Worker could not run the check: {result!r}")
        assert result[1] == [
            date.max,
            date.min,
            date.max,
            datetime.max,
            datetime.min,
            datetime.min,
        ], "EXTREME_DATE_PARSING_COMPLETES"
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


def test_ordinary_date():
    assert parse_date("2021-05-11") == date(2021, 5, 11)


def test_ordinary_millisecond_timestamp():
    assert parse_datetime(1_549_316_052_104) == datetime(
        2019, 2, 4, 21, 34, 12, 104_000, tzinfo=timezone.utc
    )
