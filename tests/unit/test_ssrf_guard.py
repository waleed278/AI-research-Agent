import socket

import pytest

from app.tools.ssrf_guard import UnsafeUrlError, validate_public_url


def test_rejects_non_http_scheme() -> None:
    with pytest.raises(UnsafeUrlError, match="Scheme"):
        validate_public_url("file:///etc/passwd")


def test_rejects_loopback_ip_literal() -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        validate_public_url("http://127.0.0.1/secret")


def test_rejects_cloud_metadata_ip_literal() -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        validate_public_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_private_rfc1918_ip_literal() -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        validate_public_url("http://10.0.0.5/internal-api")


def test_rejects_hostname_with_no_hostname_component() -> None:
    with pytest.raises(UnsafeUrlError, match="no hostname"):
        validate_public_url("http:///path-only")


def test_accepts_hostname_resolving_to_a_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: object) -> list[tuple]:
        assert host == "safe.example.com"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert validate_public_url("https://safe.example.com/article") == "https://safe.example.com/article"


def test_rejects_hostname_that_resolves_to_a_private_address(monkeypatch: pytest.MonkeyPatch) -> None:
    """The important case: a public-looking hostname whose DNS record has
    been pointed (accidentally or maliciously) at an internal address --
    rejecting by hostname alone would miss this."""

    def fake_getaddrinfo(host: str, port: object) -> list[tuple]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        validate_public_url("https://looks-public.example.com/")


def test_unresolvable_hostname_raises() -> None:
    with pytest.raises(UnsafeUrlError, match="Could not resolve"):
        validate_public_url("http://this-domain-should-not-exist.invalid/")
