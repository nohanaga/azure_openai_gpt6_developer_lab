"""Mirror Python console output to span events without delaying notebook output."""

import sys
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from typing import TextIO

from opentelemetry.trace import Span


class _Tee:
    def __init__(self, stream: TextIO, captured: StringIO) -> None:
        self._stream = stream
        self._captured = captured

    def write(self, text: str) -> int:
        written = self._stream.write(text)
        self._captured.write(text)
        return written

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


@contextmanager
def trace_console(span: Span) -> Iterator[None]:
    """Record stdout/stderr before the enclosing span ends, including on errors.

    Output is forwarded immediately to the existing notebook streams. Capture
    Python stream writes only; do not redirect file descriptors or IPython's
    rich-display publisher. Use within one sequential notebook cell at a time.
    """
    stdout, stderr = StringIO(), StringIO()
    try:
        with (
            redirect_stdout(_Tee(sys.stdout, stdout)),
            redirect_stderr(_Tee(sys.stderr, stderr)),
        ):
            yield
    finally:
        # Aggregate writes so print's fragments do not exhaust the event limit.
        for name, captured in (("stdout", stdout), ("stderr", stderr)):
            text = captured.getvalue()
            if text:
                span.add_event(f"notebook.{name}", {"output": text})
