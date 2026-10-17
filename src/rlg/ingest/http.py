"""Polite HTTP GET: rate limited, identifies us, honours 503 Retry-After, 404 -> None."""

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping

from rlg.ingest.ratelimit import RateLimiter

Transport = Callable[[str, Mapping[str, str]], tuple[int, bytes, Mapping[str, str]]]
"""(url, headers) -> (status, body, response headers)."""


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} for {url}")
        self.status = status


def urllib_transport(url: str, headers: Mapping[str, str]) -> tuple[int, bytes, Mapping[str, str]]:
    req = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})


class PoliteHttp:
    def __init__(
        self,
        limiter: RateLimiter,
        user_agent: str,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.limiter = limiter
        self.headers = {"User-Agent": user_agent, **(extra_headers or {})}
        self.transport = transport
        self.sleep = sleep
        self.max_retries = max_retries

    def get(self, url: str, params: Mapping[str, str] | None = None) -> bytes | None:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            status, body, headers = self.transport(url, self.headers)
            if status == 200:
                return body
            if status == 404:
                return None
            if status in (429, 503) and attempt < self.max_retries:
                retry_after = headers.get("Retry-After") or headers.get("retry-after") or "10"
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = 10.0
                self.sleep(min(delay, 600.0))
                continue
            raise HttpError(status, url)
        raise HttpError(503, url)
