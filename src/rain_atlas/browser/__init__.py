"""Research Browser Adapter: authorized retrieval with provenance.

Structured observation, action verification and provenance capture without
a model dependency:

* :class:`BrowserSession` -- fetch a URL and observe it as a *structured*
  page state (title, text, links) instead of raw HTML;
* provenance capture: every observation records its URL, fetch time and
  content hash, so retrieved information is evidence, not hearsay;
* action verification: ``expect_text`` turns a fetch into a *verified
  observation* only when the expected content is present;
* authorized use only: the adapter takes explicit URLs and never circumvents
  access controls; robots/ToS compliance is the caller's responsibility;
* fully offline in tests via ``file://`` or local HTTP.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

from ..canonical import sha256_bytes


class BrowserError(RuntimeError):
    """A fetch or observation failed."""


@dataclass
class PageObservation:
    """The structured state of one fetched page."""

    url: str
    title: str = ""
    text: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    fetched_at_ms: float = 0.0
    content_hash: str = ""
    verified: bool = False
    verification_note: str = ""
    final_url: str = ""  # after redirects; the URL the content actually came from

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "final_url": self.final_url or self.url,
            "title": self.title,
            "text": self.text,
            "links": list(self.links),
            "fetched_at_ms": self.fetched_at_ms,
            "content_hash": self.content_hash,
            "verified": self.verified,
            "verification_note": self.verification_note,
        }


class _TextExtractor(HTMLParser):
    """Collect title, visible text and hyperlinks from HTML."""

    _SKIP = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._skip_depth = 0
        self._in_title = False
        self._current_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = next((value for key, value in attrs if key == "href"), "")
            self._current_href = href or ""
        elif tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a":
            self._current_href = ""

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.text_parts.append(data)
            if self._current_href:
                stripped = data.strip()
                if stripped and len(self.links) < 500:
                    self.links.append({"href": self._current_href, "text": stripped[:200]})


class BrowserSession:
    """A stateless, offline-capable observation adapter."""

    MAX_BYTES = 10 * 1024 * 1024

    def __init__(
        self, *, clock: Any | None = None, timeout_s: float = 15.0, max_bytes: int = MAX_BYTES
    ) -> None:
        self._clock = clock or (lambda: time.time() * 1000.0)
        self._timeout_s = timeout_s
        self._max_bytes = max_bytes
        self.observations: list[PageObservation] = []

    def _bounded(self, url: str, handle: Any) -> bytes:
        body = handle.read(self._max_bytes + 1)
        if len(body) > self._max_bytes:
            raise BrowserError(f"{url} exceeds the {self._max_bytes}-byte observation limit")
        return body

    def fetch(
        self,
        url: str,
        *,
        expect_text: str | None = None,
        base_url: str | None = None,
    ) -> PageObservation:
        """Fetch *url* and return its structured observation.

        With ``expect_text``, the observation is *verified* only when the
        substring is present, mirroring the reference's action-verification
        concept. ``base_url`` resolves relative links in the observation.
        """

        scheme = urlparse(url).scheme
        if scheme not in ("http", "https", "file"):
            raise BrowserError(f"unsupported URL scheme {scheme!r} for {url}")
        charset = "utf-8"
        final_url = url
        try:
            if scheme == "file":
                from urllib.request import url2pathname

                with open(url2pathname(urlparse(url).path), "rb") as handle:
                    body = self._bounded(url, handle)
            else:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "rain-atlas-research/0.1 (authorized fetch)"}
                )
                with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                    body = self._bounded(url, response)
                    final_url = response.geturl() or url
                    charset = response.headers.get_content_charset() or "utf-8"
        except (urllib.error.URLError, OSError) as exc:
            raise BrowserError(f"fetch of {url} failed: {exc}") from exc

        try:
            html = body.decode(charset, errors="replace")
        except LookupError:  # unknown charset label from the server
            html = body.decode("utf-8", errors="replace")
        extractor = _TextExtractor()
        try:
            extractor.feed(html)
        except Exception as exc:  # noqa: BLE001 - malformed HTML is data, not a crash
            raise BrowserError(f"could not parse page at {url}: {exc}") from exc

        text = " ".join(" ".join(extractor.text_parts).split())
        base = base_url or final_url
        links = [{"href": urljoin(base, link["href"]), "text": link["text"]} for link in extractor.links]
        observation = PageObservation(
            url=url,
            final_url=final_url,
            title=" ".join("".join(extractor.title_parts).split()),
            text=text,
            links=links,
            fetched_at_ms=self._clock(),
            content_hash=sha256_bytes(body),
        )
        if expect_text is not None:
            haystack = f"{observation.title} {text}".lower()
            observation.verified = expect_text.lower() in haystack
            observation.verification_note = (
                f"expected {expect_text!r} {'present' if observation.verified else 'absent'}"
            )
        self.observations.append(observation)
        return observation

    def history(self) -> list[dict[str, Any]]:
        return [observation.to_dict() for observation in self.observations]
