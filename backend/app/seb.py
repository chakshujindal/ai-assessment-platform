"""Safe Exam Browser (SEB) request verification.

When "Send Browser Exam Key" is on, SEB adds the header X-SafeExamBrowser-RequestHash to
every request: SHA-256 (lowercase hex) of the absolute request URL, without any #fragment,
immediately followed by the Browser Exam Key (BEK). The BEK itself is a hash of the SEB
config file plus the SEB build, so a matching header shows the request came from SEB
running the exact config the recruiter set up.
"""

import hashlib
import hmac
from urllib.parse import urlsplit, urlunsplit

HEADER = "X-SafeExamBrowser-RequestHash"


def request_hash(url: str, browser_exam_key: str) -> str:
    url_without_fragment = url.split("#", 1)[0]
    return hashlib.sha256((url_without_fragment + browser_exam_key).encode()).hexdigest()


def verify_request_hash(url: str, browser_exam_key: str, header_value: str | None) -> bool:
    """True only if the header matches; compared in constant time."""
    if not header_value or not browser_exam_key:
        return False
    expected = request_hash(url, browser_exam_key.strip())
    return hmac.compare_digest(expected, header_value.strip().lower())


def public_url(server_url: str, public_base_url: str) -> str:
    """Rebuild the URL the browser actually requested when we sit behind a proxy.

    SEB hashes the URL it sent, e.g. https://exams.example.com/api/take/abc, while the app
    may see http://127.0.0.1:8000/api/take/abc. PUBLIC_BASE_URL fixes up scheme and host.
    """
    if not public_base_url:
        return server_url
    base = urlsplit(public_base_url.rstrip("/"))
    seen = urlsplit(server_url)
    return urlunsplit((base.scheme, base.netloc, base.path + seen.path, seen.query, ""))
