import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrlError(ValueError):
    """Raised when a URL the agent chose to fetch resolves somewhere it
    shouldn't -- loopback, link-local (including the 169.254.169.254 cloud
    metadata endpoint), private RFC1918 ranges, or a non-http(s) scheme."""


def _is_unsafe_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> str:
    """Raises UnsafeUrlError if the URL is not safe for the agent to fetch.
    Returns the normalized URL on success.

    This is a defense against SSRF: the agent picks URLs from search results
    autonomously, so a malicious or compromised search result pointing at
    `http://169.254.169.254/latest/meta-data/` or an internal service must be
    rejected before we ever open a socket to it -- rejecting by hostname
    alone is not enough because DNS can resolve a public-looking hostname to
    a private IP, so we resolve first and check the actual address.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"Scheme '{parsed.scheme}' is not allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname")

    try:
        resolved = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve hostname: {exc}") from exc

    for _family, _type, _proto, _canonname, sockaddr in resolved:
        ip_str = str(sockaddr[0])
        if _is_unsafe_ip(ip_str):
            raise UnsafeUrlError(f"Hostname resolves to disallowed address {ip_str}")

    return url
