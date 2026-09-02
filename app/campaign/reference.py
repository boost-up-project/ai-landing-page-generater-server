from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from app.campaign.componentization import sanitize_html

_SECTION_PATTERN = re.compile(
    r"<(header|section|article|footer)\b[^>]*>", re.IGNORECASE
)


def normalize_public_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Reference URL must be a public http:// or https:// address")
    if parsed.username or parsed.password:
        raise ValueError("Reference URL cannot include credentials")
    return candidate


async def fetch_public_html(value: str, *, max_size_bytes: int) -> tuple[str, str]:
    """Fetch public HTML and re-check every redirect target to prevent SSRF."""
    current = normalize_public_url(value)
    for _ in range(4):
        parsed = urlsplit(current)
        await _resolve_public_host(
            parsed.hostname or "",
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=10,
                trust_env=False,
            ) as client:
                response = await client.get(
                    current,
                    headers={"Accept": "text/html,application/xhtml+xml"},
                )
        except httpx.HTTPError as exc:
            raise ValueError("Reference URL could not be fetched") from exc
        if response.status_code in {301, 302, 303, 307, 308}:
            target = response.headers.get("location")
            if not target:
                raise ValueError("Reference URL returned an invalid redirect")
            current = normalize_public_url(urljoin(current, target))
            continue
        if response.is_error:
            raise ValueError(f"Reference URL returned HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "").casefold()
        if "html" not in content_type:
            raise ValueError("Reference URL must return an HTML page")
        if len(response.content) > max_size_bytes:
            raise ValueError("Reference URL page exceeds the size limit")
        return current, sanitize_html(response.text)
    raise ValueError("Reference URL redirected too many times")


async def _resolve_public_host(hostname: str, port: int) -> None:
    try:
        addresses = await asyncio.get_running_loop().run_in_executor(
            None,
            socket.getaddrinfo,
            hostname,
            port,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("Reference URL hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("Reference URL hostname could not be resolved")
    for address in addresses:
        host = address[4][0]
        try:
            ip = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("Reference URL hostname could not be resolved") from exc
        if not ip.is_global:
            raise ValueError("Reference URL must resolve to a public address")


def reference_layout_summary(source: str) -> dict[str, int | list[str]]:
    """A non-textual structure summary is safe to give the layout planner."""
    tags = [match.group(1).casefold() for match in _SECTION_PATTERN.finditer(source)]
    return {
        "section_order": tags[:30],
        "section_count": len(tags),
        "heading_count": len(re.findall(r"<h[1-6]\b", source, re.IGNORECASE)),
        "image_count": len(
            re.findall(r"<(?:img|picture|video)\b", source, re.IGNORECASE)
        ),
        "cta_count": len(re.findall(r"<(?:a|button)\b", source, re.IGNORECASE)),
    }
