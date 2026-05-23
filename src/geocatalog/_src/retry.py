"""Retry helpers for transient remote I/O failures."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger as log
from rasterio.errors import RasterioIOError
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)


try:
    from urllib3.exceptions import ReadTimeoutError
except ImportError:  # pragma: no cover - urllib3 is optional at runtime
    _TRANSIENT_IO_ERRORS = (RasterioIOError, OSError)
else:
    _TRANSIENT_IO_ERRORS = (RasterioIOError, OSError, ReadTimeoutError)


_RETRY_WAIT = wait_exponential(multiplier=1, min=1) + wait_random(0, 1)


def _log_before_sleep(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome is not None else None
    sleep = (
        retry_state.next_action.sleep if retry_state.next_action is not None else 0.0
    )
    log.warning(
        "Transient I/O error on attempt {}; retrying in {:.2f}s: {}",
        retry_state.attempt_number,
        sleep,
        exc,
    )


def retry_transient_io[T](
    fn: Callable[..., T],
    *args: Any,
    retries: int,
    **kwargs: Any,
) -> T:
    """Call ``fn`` with retries for transient remote I/O exceptions."""
    if retries < 0:
        raise ValueError(f"retries must be >= 0; got {retries}")
    if retries == 0:
        return fn(*args, **kwargs)

    retryer = Retrying(
        retry=retry_if_exception_type(_TRANSIENT_IO_ERRORS),
        stop=stop_after_attempt(retries + 1),
        wait=_RETRY_WAIT,
        before_sleep=_log_before_sleep,
        reraise=True,
    )
    return retryer(fn, *args, **kwargs)
