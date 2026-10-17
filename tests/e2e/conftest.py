"""e2e tests run with the network blocked unless RLG_LIVE=1."""

import os
import socket
from collections.abc import Iterator

import pytest


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[object]]:
    attempts: list[object] = []
    if os.environ.get("RLG_LIVE") == "1":
        yield attempts
        return

    def guard(self: socket.socket, address: object) -> None:
        attempts.append(address)
        raise NetworkBlocked(f"network call to {address} during e2e test")

    def dns_guard(*args: object, **kwargs: object) -> None:
        attempts.append(args[:2])
        raise NetworkBlocked(f"network call (DNS) to {args[:2]} during e2e test")

    monkeypatch.setattr(socket, "getaddrinfo", dns_guard)
    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    yield attempts
