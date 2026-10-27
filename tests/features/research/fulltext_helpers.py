"""Shared helpers for full-text retrieval tests (no real network access)."""

from collections.abc import Callable

import httpx

PDF_BYTES = b"%PDF-1.4\n%fake pdf body\n"

Responder = Callable[[httpx.Request], httpx.Response]


class FakeWeb:
    """Maps ``host + path`` to canned responses and records every request.

    A route value may be a response, a list of responses (served in order, the
    last one repeating) or a callable taking the request. Unknown URLs fail the
    test so nothing can silently reach the network.
    """

    def __init__(self) -> None:
        self.routes: dict[str, object] = {}
        self.requests: list[httpx.Request] = []

    def add(self, url: str, response: object) -> "FakeWeb":
        self.routes[url] = response
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.url.host}{request.url.path}"
        if key not in self.routes:
            raise AssertionError(f"unexpected request: {request.url}")
        route = self.routes[key]
        if callable(route):
            return route(request)
        if isinstance(route, list):
            return route.pop(0) if len(route) > 1 else route[0]
        return route  # type: ignore[return-value]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler),
            follow_redirects=True,
            headers={"User-Agent": "test"},
        )

    def hosts_called(self) -> list[str]:
        return [f"{r.url.host}{r.url.path}" for r in self.requests]


def pdf_response() -> httpx.Response:
    return httpx.Response(
        200, content=PDF_BYTES, headers={"content-type": "application/pdf"}
    )


def jats(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<sec><title>Section {i}</title><p>{p}</p></sec>"
        for i, p in enumerate(paragraphs)
    )
    return (
        "<article><front><article-meta/></front>"
        f"<body>{body}<fig><p>FIGURE CAPTION</p></fig></body></article>"
    ).encode()
