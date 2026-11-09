"""Run the Chaos Store in a background thread (tests and measuring scripts)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn

from chaos_store.app import create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@contextmanager
def serve_in_thread(port: int | None = None, *, control: bool = True) -> Iterator[str]:
    """Yield the base URL of a running store; stop it on exit."""
    port = port or free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(control=control), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            server.should_exit = True
            raise RuntimeError("Chaos Store did not start")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
