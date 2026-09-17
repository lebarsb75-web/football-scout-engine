import hmac
import ipaddress
import os
from urllib.parse import urlparse


def _allowed_video_hosts() -> set[str]:
    raw = os.getenv("VIDEO_HOST_ALLOWLIST", "")
    return {host.strip().lower().rstrip(".") for host in raw.split(",") if host.strip()}


def validate_video_url_for_submission(url: str) -> None:
    """Fail closed before a paid worker is allowed to fetch a user-provided URL.

    The production upload flow should use object storage and short-lived signed URLs.
    Until then, paid submission requires an explicit hostname allowlist.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Video URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in video URLs are not allowed")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("Video URL must contain a hostname")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Localhost video URLs are not allowed")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None

    if ip is not None and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise ValueError("Private or non-public IP video URLs are not allowed")

    allowlist = _allowed_video_hosts()
    if not allowlist:
        raise ValueError(
            "Paid video submission is locked until VIDEO_HOST_ALLOWLIST is configured"
        )

    if not any(host == allowed or host.endswith("." + allowed) for allowed in allowlist):
        raise ValueError("Video hostname is not in VIDEO_HOST_ALLOWLIST")


def approval_secret_configured() -> bool:
    return bool(os.getenv("COST_APPROVAL_SECRET", "").strip())


def approval_secret_matches(provided: str | None) -> bool:
    expected = os.getenv("COST_APPROVAL_SECRET", "")
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)
