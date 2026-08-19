"""
OSGuide Engine
Security Guard Layer

Purpose
-------
This module centralizes the defensive controls used by the OSGuide
Discovery Engine before any future live network, Supabase, APK, GitHub,
F-Droid, content, or AI integration is allowed to operate.

It provides:
- strict input normalization
- package ID validation
- URL validation
- SSRF protection
- hostname allow/deny policy
- scheme and port restrictions
- credential presence checks without credential disclosure
- secret redaction
- dangerous environment-variable detection
- safe path handling
- safe filename handling
- bounded text and JSON handling
- response-size guards
- redirect policy helpers
- GitHub URL validation
- F-Droid URL validation
- APK URL validation
- Supabase URL validation
- content-type validation
- checksum validation
- SHA-256 helpers
- basic archive/path traversal guards
- security findings
- security reports
- fail-closed policy evaluation
- diagnostics for GitHub Actions

Architecture rules
------------------
1. The security layer never publishes applications.
2. The security layer never decides final OSGuide application actions.
3. The security layer never stores credentials.
4. The security layer never prints secret values.
5. service_role secrets are forbidden in public/client code.
6. Private network destinations are rejected by default.
7. Loopback, link-local and metadata-service addresses are rejected.
8. URL userinfo is forbidden.
9. Non-HTTPS URLs are rejected by default.
10. Redirects must be revalidated after every hop by the caller.
11. Arbitrary ports are forbidden by default.
12. Hostname suffix checks are boundary-aware.
13. DNS resolution is treated as untrusted input.
14. Resolved private IP addresses are rejected.
15. Package IDs must pass strict Android-like validation.
16. Filenames are normalized and path traversal is rejected.
17. APK candidates must come from trusted hosts or explicit policy.
18. Checksums must use approved algorithms.
19. MD5 and SHA-1 are not accepted for security verification.
20. Raw APK bytes are never logged.
21. Raw HTML/API payloads are never logged.
22. JSON size and nesting are bounded.
23. Text fields are bounded before further processing.
24. Secret-like mappings are recursively redacted.
25. Authorization, cookies and tokens are always sensitive.
26. JWT-looking values are always sensitive.
27. GitHub tokens must be supplied only through GitHub Actions Secrets.
28. Supabase write credentials must never be embedded in repository files.
29. AI provider keys must never be embedded in repository files.
30. Public Supabase URL values may exist where required, but secret keys may not.
31. Dynamic code execution is forbidden.
32. eval/exec-like configuration behavior is forbidden.
33. Shell execution is outside this module.
34. Untrusted file extraction is outside this module.
35. Security failures default to block/review rather than silent continuation.
36. Admin-owned fields remain protected elsewhere and are not overridden here.
37. Tombstones remain protected elsewhere and are not cleared here.
38. This module uses only the Python standard library.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import unicodedata
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    Final,
    Iterable,
    Mapping,
    MutableMapping,
    Sequence,
)
from urllib.parse import (
    ParseResult,
    quote,
    unquote,
    urlparse,
    urlunparse,
)


# ============================================================
# Component identity
# ============================================================

SECURITY_COMPONENT: Final[str] = "Security Guard"
SECURITY_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Limits
# ============================================================

DEFAULT_MAX_TEXT_LENGTH: Final[int] = 8_000
HARD_MAX_TEXT_LENGTH: Final[int] = 100_000

DEFAULT_MAX_JSON_BYTES: Final[int] = 2_000_000
HARD_MAX_JSON_BYTES: Final[int] = 20_000_000

DEFAULT_MAX_JSON_DEPTH: Final[int] = 12
HARD_MAX_JSON_DEPTH: Final[int] = 32

DEFAULT_MAX_JSON_ITEMS: Final[int] = 10_000
HARD_MAX_JSON_ITEMS: Final[int] = 100_000

DEFAULT_MAX_URL_LENGTH: Final[int] = 2_048
HARD_MAX_URL_LENGTH: Final[int] = 8_192

DEFAULT_MAX_DOWNLOAD_BYTES: Final[int] = 250_000_000
HARD_MAX_DOWNLOAD_BYTES: Final[int] = 2_000_000_000

DEFAULT_MAX_REDIRECTS: Final[int] = 5
HARD_MAX_REDIRECTS: Final[int] = 10

DEFAULT_MAX_FILENAME_LENGTH: Final[int] = 180
HARD_MAX_FILENAME_LENGTH: Final[int] = 255

DEFAULT_DNS_TIMEOUT_SECONDS: Final[float] = 5.0
HARD_DNS_TIMEOUT_SECONDS: Final[float] = 15.0


# ============================================================
# Regexes
# ============================================================

PACKAGE_SEGMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*$"
)

HEX_64_RE: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{64}$"
)

HOST_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)

SECRET_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:"
    r"secret|token|password|passwd|authorization|cookie|session|"
    r"api[_-]?key|service[_-]?role|private[_-]?key|access[_-]?key|"
    r"refresh[_-]?token|client[_-]?secret|bearer|credential"
    r")"
)

JWT_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$"
)

LONG_SECRET_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9+/=_-]{48,}$"
)

CONTROL_CHAR_RE: Final[re.Pattern[str]] = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)

WINDOWS_DRIVE_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z]:"
)


# ============================================================
# Trusted host defaults
# ============================================================

DEFAULT_GITHUB_HOSTS: Final[tuple[str, ...]] = (
    "github.com",
    "raw.githubusercontent.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "githubusercontent.com",
)

DEFAULT_FDROID_HOSTS: Final[tuple[str, ...]] = (
    "f-droid.org",
    "fdroid.gitlab.io",
    "gitlab.com",
)

DEFAULT_SUPABASE_SUFFIXES: Final[tuple[str, ...]] = (
    ".supabase.co",
    ".supabase.in",
)

DEFAULT_BLOCKED_HOSTS: Final[tuple[str, ...]] = (
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata.google.internal.",
    "instance-data",
)

DEFAULT_ALLOWED_SCHEMES: Final[tuple[str, ...]] = (
    "https",
)

DEFAULT_ALLOWED_PORTS: Final[tuple[int, ...]] = (
    443,
)

DEFAULT_APK_CONTENT_TYPES: Final[tuple[str, ...]] = (
    "application/vnd.android.package-archive",
    "application/octet-stream",
    "binary/octet-stream",
)

DEFAULT_JSON_CONTENT_TYPES: Final[tuple[str, ...]] = (
    "application/json",
    "application/problem+json",
)


# ============================================================
# Enums
# ============================================================

class SecuritySeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityDisposition(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class SecurityFindingCode(str, Enum):
    INVALID_PACKAGE_ID = "invalid-package-id"
    INVALID_URL = "invalid-url"
    URL_TOO_LONG = "url-too-long"
    URL_USERINFO = "url-userinfo"
    URL_SCHEME = "url-scheme"
    URL_PORT = "url-port"
    URL_HOST = "url-host"
    URL_PRIVATE_IP = "url-private-ip"
    URL_BLOCKED_HOST = "url-blocked-host"
    URL_DNS_FAILURE = "url-dns-failure"
    URL_DNS_PRIVATE_IP = "url-dns-private-ip"
    URL_REDIRECT_LIMIT = "url-redirect-limit"
    UNTRUSTED_GITHUB_HOST = "untrusted-github-host"
    UNTRUSTED_FDROID_HOST = "untrusted-fdroid-host"
    UNTRUSTED_APK_HOST = "untrusted-apk-host"
    INVALID_SUPABASE_URL = "invalid-supabase-url"
    DANGEROUS_SECRET_NAME = "dangerous-secret-name"
    EMBEDDED_SECRET = "embedded-secret"
    INVALID_CHECKSUM = "invalid-checksum"
    UNSAFE_FILENAME = "unsafe-filename"
    PATH_TRAVERSAL = "path-traversal"
    INVALID_CONTENT_TYPE = "invalid-content-type"
    RESPONSE_TOO_LARGE = "response-too-large"
    JSON_TOO_LARGE = "json-too-large"
    JSON_TOO_DEEP = "json-too-deep"
    JSON_TOO_MANY_ITEMS = "json-too-many-items"
    INVALID_JSON = "invalid-json"
    CONTROL_CHARACTERS = "control-characters"
    DYNAMIC_CODE_FORBIDDEN = "dynamic-code-forbidden"
    SHELL_PAYLOAD_SUSPICIOUS = "shell-payload-suspicious"
    ENVIRONMENT_MISCONFIGURATION = "environment-misconfiguration"
    POLICY_VIOLATION = "policy-violation"


class URLPurpose(str, Enum):
    GENERIC = "generic"
    GITHUB = "github"
    FDROID = "fdroid"
    APK = "apk"
    SUPABASE = "supabase"
    AI = "ai"
    OFFICIAL = "official"


class SecretClass(str, Enum):
    NONE = "none"
    NAME = "name"
    JWT = "jwt"
    LONG_TOKEN = "long-token"
    AUTH_HEADER = "auth-header"
    COOKIE = "cookie"


# ============================================================
# Time helper
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    ).isoformat()


# ============================================================
# Finding model
# ============================================================

@dataclass(frozen=True, slots=True)
class SecurityFinding:
    code: SecurityFindingCode
    severity: SecuritySeverity
    disposition: SecurityDisposition
    message: str

    subject: str | None = None
    metadata: Mapping[str, object] = field(
        default_factory=dict
    )

    created_at: datetime = field(
        default_factory=utc_now
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "disposition": self.disposition.value,
            "message": self.message,
            "subject": self.subject,
            "metadata": safe_mapping(
                self.metadata
            ),
            "created_at": isoformat_utc(
                self.created_at
            ),
        }


@dataclass(slots=True)
class SecurityReport:
    findings: list[
        SecurityFinding
    ] = field(
        default_factory=list
    )

    started_at: datetime = field(
        default_factory=utc_now
    )

    finished_at: datetime | None = None

    def add(
        self,
        finding: SecurityFinding,
    ) -> None:
        self.findings.append(
            finding
        )

    @property
    def blocked(self) -> bool:
        return any(
            finding.disposition
            == SecurityDisposition.BLOCK
            for finding in self.findings
        )

    @property
    def review_required(self) -> bool:
        return any(
            finding.disposition
            == SecurityDisposition.REVIEW
            for finding in self.findings
        )

    @property
    def highest_severity(self) -> SecuritySeverity:
        rank = {
            SecuritySeverity.INFO: 0,
            SecuritySeverity.LOW: 1,
            SecuritySeverity.MEDIUM: 2,
            SecuritySeverity.HIGH: 3,
            SecuritySeverity.CRITICAL: 4,
        }

        if not self.findings:
            return SecuritySeverity.INFO

        return max(
            (
                finding.severity
                for finding in self.findings
            ),
            key=lambda item: rank[item],
        )

    def finish(self) -> "SecurityReport":
        self.finished_at = utc_now()
        return self

    def to_dict(self) -> dict[str, object]:
        return {
            "started_at": isoformat_utc(
                self.started_at
            ),
            "finished_at": isoformat_utc(
                self.finished_at
            ),
            "blocked": self.blocked,
            "review_required": self.review_required,
            "highest_severity": self.highest_severity.value,
            "finding_count": len(
                self.findings
            ),
            "findings": [
                finding.to_dict()
                for finding in self.findings
            ],
        }


# ============================================================
# Policy
# ============================================================

@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    allowed_schemes: tuple[str, ...] = DEFAULT_ALLOWED_SCHEMES
    allowed_ports: tuple[int, ...] = DEFAULT_ALLOWED_PORTS

    github_hosts: tuple[str, ...] = DEFAULT_GITHUB_HOSTS
    fdroid_hosts: tuple[str, ...] = DEFAULT_FDROID_HOSTS
    supabase_suffixes: tuple[str, ...] = DEFAULT_SUPABASE_SUFFIXES

    extra_trusted_apk_hosts: tuple[str, ...] = ()
    extra_official_hosts: tuple[str, ...] = ()

    blocked_hosts: tuple[str, ...] = DEFAULT_BLOCKED_HOSTS

    require_https: bool = True
    forbid_userinfo: bool = True
    forbid_private_networks: bool = True
    resolve_dns_before_network: bool = True

    max_url_length: int = DEFAULT_MAX_URL_LENGTH
    max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES
    max_redirects: int = DEFAULT_MAX_REDIRECTS

    max_json_bytes: int = DEFAULT_MAX_JSON_BYTES
    max_json_depth: int = DEFAULT_MAX_JSON_DEPTH
    max_json_items: int = DEFAULT_MAX_JSON_ITEMS

    max_text_length: int = DEFAULT_MAX_TEXT_LENGTH
    max_filename_length: int = DEFAULT_MAX_FILENAME_LENGTH

    require_sha256_for_apk: bool = True

    allow_http_for_local_diagnostics: bool = False

    fail_closed_on_dns_error: bool = True

    def validate(self) -> None:
        if not self.allowed_schemes:
            raise ValueError(
                "At least one URL scheme must be allowed."
            )

        if self.require_https and "https" not in self.allowed_schemes:
            raise ValueError(
                "HTTPS is required but not allowed."
            )

        for port in self.allowed_ports:
            if not 1 <= int(port) <= 65535:
                raise ValueError(
                    "Invalid allowed port."
                )

        if not (
            128
            <= self.max_url_length
            <= HARD_MAX_URL_LENGTH
        ):
            raise ValueError(
                "max_url_length outside allowed range."
            )

        if not (
            1_000_000
            <= self.max_download_bytes
            <= HARD_MAX_DOWNLOAD_BYTES
        ):
            raise ValueError(
                "max_download_bytes outside allowed range."
            )

        if not (
            0
            <= self.max_redirects
            <= HARD_MAX_REDIRECTS
        ):
            raise ValueError(
                "max_redirects outside allowed range."
            )

        if not (
            1_000
            <= self.max_json_bytes
            <= HARD_MAX_JSON_BYTES
        ):
            raise ValueError(
                "max_json_bytes outside allowed range."
            )

        if not (
            1
            <= self.max_json_depth
            <= HARD_MAX_JSON_DEPTH
        ):
            raise ValueError(
                "max_json_depth outside allowed range."
            )

        if not (
            1
            <= self.max_json_items
            <= HARD_MAX_JSON_ITEMS
        ):
            raise ValueError(
                "max_json_items outside allowed range."
            )

        if not (
            128
            <= self.max_text_length
            <= HARD_MAX_TEXT_LENGTH
        ):
            raise ValueError(
                "max_text_length outside allowed range."
            )

        if not (
            32
            <= self.max_filename_length
            <= HARD_MAX_FILENAME_LENGTH
        ):
            raise ValueError(
                "max_filename_length outside allowed range."
            )

        if not self.forbid_private_networks:
            raise ValueError(
                "Private-network blocking must remain enabled."
            )

        if not self.forbid_userinfo:
            raise ValueError(
                "URL userinfo blocking must remain enabled."
            )


# ============================================================
# Text normalization
# ============================================================

def normalize_unicode_text(
    value: object,
) -> str:
    return unicodedata.normalize(
        "NFKC",
        str(value),
    )


def sanitize_text(
    value: object,
    *,
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
    allow_newlines: bool = False,
) -> str:
    text = normalize_unicode_text(
        value
    )

    text = text.replace(
        "\x00",
        "",
    )

    if CONTROL_CHAR_RE.search(
        text
    ):
        text = CONTROL_CHAR_RE.sub(
            "",
            text,
        )

    if not allow_newlines:
        text = (
            text.replace(
                "\r",
                " ",
            )
            .replace(
                "\n",
                " ",
            )
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

    else:
        text = text.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

    text = text.strip()

    if len(text) > max_length:
        text = text[:max_length]

    return text


def contains_control_characters(
    value: object,
) -> bool:
    return bool(
        CONTROL_CHAR_RE.search(
            str(value)
        )
    )


# ============================================================
# Secret classification and redaction
# ============================================================

def classify_secret(
    field_name: str,
    value: object,
) -> SecretClass:
    name = str(
        field_name
    )

    if SECRET_NAME_RE.search(
        name
    ):
        lowered = name.lower()

        if "authorization" in lowered or "bearer" in lowered:
            return SecretClass.AUTH_HEADER

        if "cookie" in lowered or "session" in lowered:
            return SecretClass.COOKIE

        return SecretClass.NAME

    if not isinstance(
        value,
        str,
    ):
        return SecretClass.NONE

    text = value.strip()

    if not text:
        return SecretClass.NONE

    if JWT_RE.fullmatch(
        text
    ):
        return SecretClass.JWT

    if LONG_SECRET_RE.fullmatch(
        text
    ):
        lowered = text.lower()

        if not lowered.startswith(
            (
                "http://",
                "https://",
                "org.",
                "com.",
                "io.",
                "net.",
            )
        ):
            return SecretClass.LONG_TOKEN

    return SecretClass.NONE


def is_secret_like(
    field_name: str,
    value: object,
) -> bool:
    return (
        classify_secret(
            field_name,
            value,
        )
        != SecretClass.NONE
    )


def safe_value(
    value: object,
    *,
    field_name: str = "",
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_JSON_DEPTH,
    max_items: int = DEFAULT_MAX_JSON_ITEMS,
    max_text_length: int = DEFAULT_MAX_TEXT_LENGTH,
) -> object:
    if is_secret_like(
        field_name,
        value,
    ):
        return "[REDACTED]"

    if depth >= max_depth:
        return "[MAX_DEPTH]"

    if value is None:
        return None

    if isinstance(
        value,
        (bool, int, float),
    ):
        return value

    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if isinstance(
        value,
        datetime,
    ):
        return isoformat_utc(
            value
        )

    if isinstance(
        value,
        str,
    ):
        return sanitize_text(
            value,
            max_length=max_text_length,
            allow_newlines=True,
        )

    if is_dataclass(
        value
    ):
        return safe_value(
            asdict(value),
            depth=depth + 1,
            max_depth=max_depth,
            max_items=max_items,
            max_text_length=max_text_length,
        )

    if isinstance(
        value,
        Mapping,
    ):
        output: dict[
            str,
            object,
        ] = {}

        for index, (key, item) in enumerate(
            value.items()
        ):
            if index >= max_items:
                output[
                    "__truncated__"
                ] = True
                break

            safe_key = sanitize_text(
                key,
                max_length=128,
            )

            if not safe_key:
                continue

            output[
                safe_key
            ] = safe_value(
                item,
                field_name=safe_key,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_text_length=max_text_length,
            )

        return output

    if isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        output_list: list[
            object
        ] = []

        for index, item in enumerate(
            value
        ):
            if index >= max_items:
                output_list.append(
                    "[TRUNCATED]"
                )
                break

            output_list.append(
                safe_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_items=max_items,
                    max_text_length=max_text_length,
                )
            )

        return output_list

    return sanitize_text(
        value,
        max_length=max_text_length,
    )


def safe_mapping(
    mapping: Mapping[str, object] | None,
) -> dict[str, object]:
    if not mapping:
        return {}

    safe = safe_value(
        mapping
    )

    if isinstance(
        safe,
        dict,
    ):
        return safe

    return {}


# ============================================================
# Package ID validation
# ============================================================

def normalize_package_id(
    value: object,
) -> str:
    return sanitize_text(
        value,
        max_length=300,
    )


def is_valid_package_id(
    value: object,
) -> bool:
    package_id = normalize_package_id(
        value
    )

    if not package_id:
        return False

    if len(
        package_id
    ) > 255:
        return False

    if package_id.startswith(
        "."
    ) or package_id.endswith(
        "."
    ):
        return False

    if ".." in package_id:
        return False

    parts = package_id.split(
        "."
    )

    if len(
        parts
    ) < 2:
        return False

    return all(
        PACKAGE_SEGMENT_RE.fullmatch(
            part
        )
        is not None
        for part in parts
    )


def validate_package_id(
    value: object,
) -> SecurityReport:
    report = SecurityReport()

    package_id = normalize_package_id(
        value
    )

    if not is_valid_package_id(
        package_id
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.INVALID_PACKAGE_ID,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Package ID does not match the accepted Android-style format."
                ),
                subject=package_id or None,
            )
        )

    return report.finish()


# ============================================================
# Hostname helpers
# ============================================================

def normalize_hostname(
    hostname: str | None,
) -> str:
    if not hostname:
        return ""

    hostname = hostname.strip().rstrip(
        "."
    ).lower()

    try:
        hostname = hostname.encode(
            "idna"
        ).decode(
            "ascii"
        )
    except UnicodeError:
        return ""

    return hostname


def is_valid_hostname(
    hostname: str,
) -> bool:
    hostname = normalize_hostname(
        hostname
    )

    if not hostname:
        return False

    if len(
        hostname
    ) > 253:
        return False

    try:
        ipaddress.ip_address(
            hostname
        )
        return True
    except ValueError:
        pass

    labels = hostname.split(
        "."
    )

    return all(
        HOST_LABEL_RE.fullmatch(
            label
        )
        is not None
        for label in labels
    )


def hostname_matches(
    hostname: str,
    candidate: str,
) -> bool:
    host = normalize_hostname(
        hostname
    )

    expected = normalize_hostname(
        candidate
    )

    if not host or not expected:
        return False

    return (
        host == expected
        or host.endswith(
            "." + expected
        )
    )


def hostname_matches_any(
    hostname: str,
    candidates: Iterable[str],
) -> bool:
    return any(
        hostname_matches(
            hostname,
            candidate,
        )
        for candidate in candidates
    )


def hostname_matches_suffix(
    hostname: str,
    suffix: str,
) -> bool:
    host = normalize_hostname(
        hostname
    )

    normalized_suffix = suffix.strip().lower()

    if not normalized_suffix:
        return False

    if normalized_suffix.startswith(
        "."
    ):
        base = normalize_hostname(
            normalized_suffix[1:]
        )

        return (
            host == base
            or host.endswith(
                "." + base
            )
        )

    return hostname_matches(
        host,
        normalized_suffix,
    )


# ============================================================
# IP safety
# ============================================================

def is_forbidden_ip(
    value: str,
) -> bool:
    try:
        address = ipaddress.ip_address(
            value
        )
    except ValueError:
        return True

    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def literal_ip_from_hostname(
    hostname: str,
) -> str | None:
    host = normalize_hostname(
        hostname
    )

    try:
        address = ipaddress.ip_address(
            host
        )
    except ValueError:
        return None

    return str(
        address
    )


def resolve_hostname_ips(
    hostname: str,
    *,
    port: int = 443,
) -> tuple[str, ...]:
    host = normalize_hostname(
        hostname
    )

    if not host:
        raise ValueError(
            "Hostname cannot be empty."
        )

    results = socket.getaddrinfo(
        host,
        port,
        type=socket.SOCK_STREAM,
    )

    addresses: list[
        str
    ] = []

    for result in results:
        sockaddr = result[
            4
        ]

        if not sockaddr:
            continue

        address = str(
            sockaddr[0]
        )

        if address not in addresses:
            addresses.append(
                address
            )

    return tuple(
        addresses
    )


# ============================================================
# URL normalization
# ============================================================

def normalize_url(
    value: object,
    *,
    max_length: int = DEFAULT_MAX_URL_LENGTH,
) -> str:
    text = sanitize_text(
        value,
        max_length=max_length,
    )

    return text


def parsed_url(
    value: object,
    *,
    max_length: int = DEFAULT_MAX_URL_LENGTH,
) -> ParseResult:
    url = normalize_url(
        value,
        max_length=max_length,
    )

    if not url:
        raise ValueError(
            "URL cannot be empty."
        )

    if len(
        url
    ) > max_length:
        raise ValueError(
            "URL exceeds maximum length."
        )

    parsed = urlparse(
        url
    )

    return parsed


def canonicalize_url(
    value: object,
    *,
    policy: SecurityPolicy | None = None,
) -> str:
    policy = (
        policy
        or SecurityPolicy()
    )

    policy.validate()

    parsed = parsed_url(
        value,
        max_length=policy.max_url_length,
    )

    scheme = parsed.scheme.lower()
    hostname = normalize_hostname(
        parsed.hostname
    )

    if not scheme or not hostname:
        raise ValueError(
            "URL must include scheme and hostname."
        )

    port = parsed.port

    netloc = hostname

    if ":" in hostname and not hostname.startswith(
        "["
    ):
        netloc = (
            "["
            + hostname
            + "]"
        )

    if port is not None:
        netloc += (
            ":"
            + str(
                port
            )
        )

    path = quote(
        unquote(
            parsed.path
        ),
        safe="/:@-._~!$&'()*+,;=",
    )

    return urlunparse(
        (
            scheme,
            netloc,
            path,
            "",
            parsed.query,
            "",
        )
    )


# ============================================================
# URL validation
# ============================================================

def validate_url(
    value: object,
    *,
    purpose: URLPurpose = URLPurpose.GENERIC,
    policy: SecurityPolicy | None = None,
    resolve_dns: bool | None = None,
) -> SecurityReport:
    policy = (
        policy
        or SecurityPolicy()
    )

    policy.validate()

    report = SecurityReport()

    url = normalize_url(
        value,
        max_length=policy.max_url_length,
    )

    if not url:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.INVALID_URL,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="URL is empty.",
            )
        )

        return report.finish()

    if len(
        url
    ) > policy.max_url_length:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_TOO_LONG,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="URL exceeds configured maximum length.",
            )
        )

        return report.finish()

    try:
        parsed = urlparse(
            url
        )
    except Exception:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.INVALID_URL,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="URL parser rejected the value.",
            )
        )

        return report.finish()

    scheme = parsed.scheme.lower()

    if not scheme:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.INVALID_URL,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="URL has no scheme.",
                subject=url,
            )
        )

    elif scheme not in policy.allowed_schemes:
        allowed_local_http = (
            scheme == "http"
            and policy.allow_http_for_local_diagnostics
        )

        if not allowed_local_http:
            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.URL_SCHEME,
                    severity=SecuritySeverity.HIGH,
                    disposition=SecurityDisposition.BLOCK,
                    message=(
                        f"URL scheme is not allowed: {scheme}."
                    ),
                    subject=url,
                )
            )

    if (
        policy.require_https
        and scheme != "https"
        and not (
            scheme == "http"
            and policy.allow_http_for_local_diagnostics
        )
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_SCHEME,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="HTTPS is required.",
                subject=url,
            )
        )

    if (
        policy.forbid_userinfo
        and (
            parsed.username is not None
            or parsed.password is not None
        )
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_USERINFO,
                severity=SecuritySeverity.CRITICAL,
                disposition=SecurityDisposition.BLOCK,
                message="Credentials in URL userinfo are forbidden.",
                subject="[REDACTED_URL]",
            )
        )

    hostname = normalize_hostname(
        parsed.hostname
    )

    if not hostname or not is_valid_hostname(
        hostname
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_HOST,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="URL hostname is invalid.",
                subject=hostname or None,
            )
        )

        return report.finish()

    if hostname_matches_any(
        hostname,
        policy.blocked_hosts,
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_BLOCKED_HOST,
                severity=SecuritySeverity.CRITICAL,
                disposition=SecurityDisposition.BLOCK,
                message="URL hostname is explicitly blocked.",
                subject=hostname,
            )
        )

    try:
        port = parsed.port
    except ValueError:
        port = None

        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_PORT,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="URL port is invalid.",
                subject=hostname,
            )
        )

    if port is not None and port not in policy.allowed_ports:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_PORT,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    f"URL port is not allowed: {port}."
                ),
                subject=hostname,
            )
        )

    literal_ip = literal_ip_from_hostname(
        hostname
    )

    if (
        literal_ip is not None
        and policy.forbid_private_networks
        and is_forbidden_ip(
            literal_ip
        )
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_PRIVATE_IP,
                severity=SecuritySeverity.CRITICAL,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Literal IP destination is not allowed."
                ),
                subject=literal_ip,
            )
        )

    # Purpose-specific hostname checks.
    if purpose == URLPurpose.GITHUB:
        if not hostname_matches_any(
            hostname,
            policy.github_hosts,
        ):
            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.UNTRUSTED_GITHUB_HOST,
                    severity=SecuritySeverity.HIGH,
                    disposition=SecurityDisposition.BLOCK,
                    message="GitHub URL uses an untrusted host.",
                    subject=hostname,
                )
            )

    elif purpose == URLPurpose.FDROID:
        if not hostname_matches_any(
            hostname,
            policy.fdroid_hosts,
        ):
            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.UNTRUSTED_FDROID_HOST,
                    severity=SecuritySeverity.HIGH,
                    disposition=SecurityDisposition.BLOCK,
                    message="F-Droid URL uses an untrusted host.",
                    subject=hostname,
                )
            )

    elif purpose == URLPurpose.SUPABASE:
        if not any(
            hostname_matches_suffix(
                hostname,
                suffix,
            )
            for suffix in policy.supabase_suffixes
        ):
            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.INVALID_SUPABASE_URL,
                    severity=SecuritySeverity.CRITICAL,
                    disposition=SecurityDisposition.BLOCK,
                    message=(
                        "Supabase URL hostname does not match approved Supabase domains."
                    ),
                    subject=hostname,
                )
            )

    elif purpose == URLPurpose.APK:
        trusted_apk_hosts = (
            tuple(
                policy.fdroid_hosts
            )
            + tuple(
                policy.github_hosts
            )
            + tuple(
                policy.extra_trusted_apk_hosts
            )
        )

        if not hostname_matches_any(
            hostname,
            trusted_apk_hosts,
        ):
            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.UNTRUSTED_APK_HOST,
                    severity=SecuritySeverity.HIGH,
                    disposition=SecurityDisposition.REVIEW,
                    message=(
                        "APK URL is not on a default trusted APK host."
                    ),
                    subject=hostname,
                )
            )

    elif purpose == URLPurpose.OFFICIAL:
        if (
            policy.extra_official_hosts
            and not hostname_matches_any(
                hostname,
                policy.extra_official_hosts,
            )
        ):
            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.URL_HOST,
                    severity=SecuritySeverity.MEDIUM,
                    disposition=SecurityDisposition.REVIEW,
                    message=(
                        "Official-source URL host is outside configured official hosts."
                    ),
                    subject=hostname,
                )
            )

    should_resolve_dns = (
        policy.resolve_dns_before_network
        if resolve_dns is None
        else bool(
            resolve_dns
        )
    )

    if (
        should_resolve_dns
        and not report.blocked
        and literal_ip is None
    ):
        try:
            addresses = resolve_hostname_ips(
                hostname,
                port=(
                    port
                    or 443
                ),
            )
        except Exception as exc:
            disposition = (
                SecurityDisposition.BLOCK
                if policy.fail_closed_on_dns_error
                else SecurityDisposition.REVIEW
            )

            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.URL_DNS_FAILURE,
                    severity=SecuritySeverity.HIGH,
                    disposition=disposition,
                    message="DNS resolution failed.",
                    subject=hostname,
                    metadata={
                        "error_type": type(
                            exc
                        ).__name__,
                    },
                )
            )

        else:
            for address in addresses:
                if (
                    policy.forbid_private_networks
                    and is_forbidden_ip(
                        address
                    )
                ):
                    report.add(
                        SecurityFinding(
                            code=SecurityFindingCode.URL_DNS_PRIVATE_IP,
                            severity=SecuritySeverity.CRITICAL,
                            disposition=SecurityDisposition.BLOCK,
                            message=(
                                "Hostname resolved to a forbidden IP address."
                            ),
                            subject=hostname,
                            metadata={
                                "resolved_ip": address,
                            },
                        )
                    )

    return report.finish()


# ============================================================
# Specific URL validators
# ============================================================

def validate_github_url(
    value: object,
    *,
    policy: SecurityPolicy | None = None,
    resolve_dns: bool | None = None,
) -> SecurityReport:
    return validate_url(
        value,
        purpose=URLPurpose.GITHUB,
        policy=policy,
        resolve_dns=resolve_dns,
    )


def validate_fdroid_url(
    value: object,
    *,
    policy: SecurityPolicy | None = None,
    resolve_dns: bool | None = None,
) -> SecurityReport:
    return validate_url(
        value,
        purpose=URLPurpose.FDROID,
        policy=policy,
        resolve_dns=resolve_dns,
    )


def validate_apk_url(
    value: object,
    *,
    policy: SecurityPolicy | None = None,
    resolve_dns: bool | None = None,
) -> SecurityReport:
    return validate_url(
        value,
        purpose=URLPurpose.APK,
        policy=policy,
        resolve_dns=resolve_dns,
    )


def validate_supabase_url(
    value: object,
    *,
    policy: SecurityPolicy | None = None,
    resolve_dns: bool | None = None,
) -> SecurityReport:
    return validate_url(
        value,
        purpose=URLPurpose.SUPABASE,
        policy=policy,
        resolve_dns=resolve_dns,
    )


# ============================================================
# Redirect validation
# ============================================================

@dataclass(frozen=True, slots=True)
class RedirectDecision:
    allowed: bool
    report: SecurityReport
    normalized_url: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "normalized_url": self.normalized_url,
            "report": self.report.to_dict(),
        }


def validate_redirect_target(
    value: object,
    *,
    purpose: URLPurpose,
    redirect_index: int,
    policy: SecurityPolicy | None = None,
    resolve_dns: bool | None = None,
) -> RedirectDecision:
    policy = (
        policy
        or SecurityPolicy()
    )

    policy.validate()

    report = SecurityReport()

    if redirect_index < 0:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_REDIRECT_LIMIT,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="Redirect index cannot be negative.",
            )
        )

        return RedirectDecision(
            allowed=False,
            report=report.finish(),
            normalized_url=None,
        )

    if redirect_index > policy.max_redirects:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.URL_REDIRECT_LIMIT,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Maximum redirect count exceeded."
                ),
            )
        )

        return RedirectDecision(
            allowed=False,
            report=report.finish(),
            normalized_url=None,
        )

    target_report = validate_url(
        value,
        purpose=purpose,
        policy=policy,
        resolve_dns=resolve_dns,
    )

    report.findings.extend(
        target_report.findings
    )

    normalized = None

    if not report.blocked:
        try:
            normalized = canonicalize_url(
                value,
                policy=policy,
            )
        except Exception:
            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.INVALID_URL,
                    severity=SecuritySeverity.HIGH,
                    disposition=SecurityDisposition.BLOCK,
                    message=(
                        "Redirect target could not be canonicalized."
                    ),
                )
            )

    return RedirectDecision(
        allowed=not report.blocked,
        report=report.finish(),
        normalized_url=normalized,
    )


# ============================================================
# Content type and response-size guards
# ============================================================

def normalized_content_type(
    value: object,
) -> str:
    text = sanitize_text(
        value,
        max_length=300,
    ).lower()

    if ";" in text:
        text = text.split(
            ";",
            1,
        )[0].strip()

    return text


def validate_content_type(
    value: object,
    *,
    allowed: Sequence[str],
) -> SecurityReport:
    report = SecurityReport()

    content_type = normalized_content_type(
        value
    )

    normalized_allowed = {
        normalized_content_type(
            item
        )
        for item in allowed
    }

    if content_type not in normalized_allowed:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.INVALID_CONTENT_TYPE,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Response content type is not allowed."
                ),
                subject=content_type or None,
                metadata={
                    "allowed": sorted(
                        normalized_allowed
                    ),
                },
            )
        )

    return report.finish()


def validate_apk_content_type(
    value: object,
) -> SecurityReport:
    return validate_content_type(
        value,
        allowed=DEFAULT_APK_CONTENT_TYPES,
    )


def validate_json_content_type(
    value: object,
) -> SecurityReport:
    return validate_content_type(
        value,
        allowed=DEFAULT_JSON_CONTENT_TYPES,
    )


def validate_response_size(
    content_length: int | None,
    *,
    max_bytes: int,
) -> SecurityReport:
    report = SecurityReport()

    if content_length is None:
        return report.finish()

    try:
        length = int(
            content_length
        )
    except (TypeError, ValueError):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.RESPONSE_TOO_LARGE,
                severity=SecuritySeverity.MEDIUM,
                disposition=SecurityDisposition.REVIEW,
                message="Response length is invalid.",
            )
        )

        return report.finish()

    if length < 0:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.RESPONSE_TOO_LARGE,
                severity=SecuritySeverity.MEDIUM,
                disposition=SecurityDisposition.REVIEW,
                message="Response length cannot be negative.",
            )
        )

    elif length > max_bytes:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.RESPONSE_TOO_LARGE,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Response exceeds configured maximum size."
                ),
                metadata={
                    "content_length": length,
                    "max_bytes": max_bytes,
                },
            )
        )

    return report.finish()


# ============================================================
# SHA-256 helpers
# ============================================================

def normalize_sha256(
    value: object,
) -> str:
    return sanitize_text(
        value,
        max_length=128,
    ).lower()


def is_valid_sha256(
    value: object,
) -> bool:
    return HEX_64_RE.fullmatch(
        normalize_sha256(
            value
        )
    ) is not None


def validate_sha256(
    value: object,
) -> SecurityReport:
    report = SecurityReport()

    digest = normalize_sha256(
        value
    )

    if not is_valid_sha256(
        digest
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.INVALID_CHECKSUM,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Expected checksum is not a valid SHA-256 digest."
                ),
                subject=digest or None,
            )
        )

    return report.finish()


def sha256_bytes(
    data: bytes,
) -> str:
    return hashlib.sha256(
        data
    ).hexdigest()


def sha256_file(
    path: str | Path,
    *,
    chunk_size: int = 1024 * 1024,
    max_bytes: int | None = None,
) -> str:
    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be positive."
        )

    target = Path(
        path
    )

    digest = hashlib.sha256()

    total = 0

    with target.open(
        "rb"
    ) as handle:
        while True:
            block = handle.read(
                chunk_size
            )

            if not block:
                break

            total += len(
                block
            )

            if (
                max_bytes is not None
                and total > max_bytes
            ):
                raise ValueError(
                    "File exceeds configured hashing size limit."
                )

            digest.update(
                block
            )

    return digest.hexdigest()


def checksum_matches(
    expected_sha256: object,
    actual_sha256: object,
) -> bool:
    expected = normalize_sha256(
        expected_sha256
    )

    actual = normalize_sha256(
        actual_sha256
    )

    return (
        is_valid_sha256(
            expected
        )
        and is_valid_sha256(
            actual
        )
        and hashlib.compare_digest(
            expected,
            actual,
        )
    )


# ============================================================
# Filename safety
# ============================================================

FORBIDDEN_FILENAME_CHARS: Final[set[str]] = set(
    '<>:"/\\|?*\x00'
)

WINDOWS_RESERVED_NAMES: Final[set[str]] = {
    "con",
    "prn",
    "aux",
    "nul",
    *{
        f"com{index}"
        for index in range(
            1,
            10,
        )
    },
    *{
        f"lpt{index}"
        for index in range(
            1,
            10,
        )
    },
}


def normalize_filename(
    value: object,
    *,
    max_length: int = DEFAULT_MAX_FILENAME_LENGTH,
) -> str:
    filename = sanitize_text(
        value,
        max_length=max_length,
    )

    filename = "".join(
        "_"
        if character in FORBIDDEN_FILENAME_CHARS
        else character
        for character in filename
    )

    filename = filename.strip(
        " ."
    )

    filename = re.sub(
        r"\s+",
        " ",
        filename,
    )

    if len(
        filename
    ) > max_length:
        filename = filename[
            :max_length
        ]

    return filename


def is_safe_filename(
    value: object,
) -> bool:
    raw = sanitize_text(
        value,
        max_length=HARD_MAX_FILENAME_LENGTH,
    )

    if not raw:
        return False

    if raw in {
        ".",
        "..",
    }:
        return False

    if "/" in raw or "\\" in raw:
        return False

    if any(
        character in FORBIDDEN_FILENAME_CHARS
        for character in raw
    ):
        return False

    normalized = normalize_filename(
        raw
    )

    if not normalized:
        return False

    stem = normalized.split(
        ".",
        1,
    )[0].lower()

    if stem in WINDOWS_RESERVED_NAMES:
        return False

    return True


def validate_filename(
    value: object,
) -> SecurityReport:
    report = SecurityReport()

    if not is_safe_filename(
        value
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.UNSAFE_FILENAME,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="Filename is unsafe.",
                subject=normalize_filename(
                    value
                ) or None,
            )
        )

    return report.finish()


# ============================================================
# Path traversal guards
# ============================================================

def has_path_traversal(
    value: object,
) -> bool:
    raw = sanitize_text(
        value,
        max_length=4_096,
        allow_newlines=False,
    )

    if not raw:
        return False

    decoded = unquote(
        raw
    )

    normalized = decoded.replace(
        "\\",
        "/",
    )

    if WINDOWS_DRIVE_RE.match(
        normalized
    ):
        return True

    if normalized.startswith(
        "/"
    ):
        return True

    parts = PurePosixPath(
        normalized
    ).parts

    return ".." in parts


def validate_relative_path(
    value: object,
) -> SecurityReport:
    report = SecurityReport()

    raw = sanitize_text(
        value,
        max_length=4_096,
    )

    if has_path_traversal(
        raw
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.PATH_TRAVERSAL,
                severity=SecuritySeverity.CRITICAL,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Relative path contains traversal or absolute-path syntax."
                ),
                subject=raw or None,
            )
        )

    return report.finish()


def safe_join(
    base: str | Path,
    relative: str,
) -> Path:
    path_report = validate_relative_path(
        relative
    )

    if path_report.blocked:
        raise ValueError(
            "Unsafe relative path."
        )

    base_path = Path(
        base
    ).resolve()

    candidate = (
        base_path
        / relative
    ).resolve()

    try:
        candidate.relative_to(
            base_path
        )
    except ValueError as exc:
        raise ValueError(
            "Resolved path escapes base directory."
        ) from exc

    return candidate


# ============================================================
# JSON structural guards
# ============================================================

@dataclass(slots=True)
class JsonStructureStats:
    depth: int = 0
    items: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "depth": self.depth,
            "items": self.items,
        }


def measure_json_structure(
    value: object,
) -> JsonStructureStats:
    stats = JsonStructureStats()

    def walk(
        node: object,
        depth: int,
    ) -> None:
        stats.depth = max(
            stats.depth,
            depth,
        )

        stats.items += 1

        if isinstance(
            node,
            Mapping,
        ):
            for key, item in node.items():
                stats.items += 1
                walk(
                    key,
                    depth + 1,
                )
                walk(
                    item,
                    depth + 1,
                )

        elif isinstance(
            node,
            Sequence,
        ) and not isinstance(
            node,
            (str, bytes, bytearray),
        ):
            for item in node:
                walk(
                    item,
                    depth + 1,
                )

    walk(
        value,
        1,
    )

    return stats


def safe_json_loads(
    raw: str | bytes,
    *,
    policy: SecurityPolicy | None = None,
) -> object:
    policy = (
        policy
        or SecurityPolicy()
    )

    policy.validate()

    encoded = (
        raw
        if isinstance(
            raw,
            bytes,
        )
        else raw.encode(
            "utf-8"
        )
    )

    if len(
        encoded
    ) > policy.max_json_bytes:
        raise ValueError(
            "JSON payload exceeds maximum size."
        )

    try:
        value = json.loads(
            encoded.decode(
                "utf-8"
            )
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "Invalid JSON payload."
        ) from exc

    stats = measure_json_structure(
        value
    )

    if stats.depth > policy.max_json_depth:
        raise ValueError(
            "JSON payload exceeds maximum nesting depth."
        )

    if stats.items > policy.max_json_items:
        raise ValueError(
            "JSON payload exceeds maximum item count."
        )

    return value


def validate_json_payload(
    raw: str | bytes,
    *,
    policy: SecurityPolicy | None = None,
) -> SecurityReport:
    policy = (
        policy
        or SecurityPolicy()
    )

    policy.validate()

    report = SecurityReport()

    encoded = (
        raw
        if isinstance(
            raw,
            bytes,
        )
        else raw.encode(
            "utf-8"
        )
    )

    if len(
        encoded
    ) > policy.max_json_bytes:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.JSON_TOO_LARGE,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "JSON payload exceeds configured maximum size."
                ),
                metadata={
                    "bytes": len(
                        encoded
                    ),
                    "max_bytes": policy.max_json_bytes,
                },
            )
        )

        return report.finish()

    try:
        value = json.loads(
            encoded.decode(
                "utf-8"
            )
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.INVALID_JSON,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message="JSON payload is invalid.",
            )
        )

        return report.finish()

    stats = measure_json_structure(
        value
    )

    if stats.depth > policy.max_json_depth:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.JSON_TOO_DEEP,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "JSON payload nesting depth exceeds configured maximum."
                ),
                metadata={
                    "depth": stats.depth,
                    "max_depth": policy.max_json_depth,
                },
            )
        )

    if stats.items > policy.max_json_items:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.JSON_TOO_MANY_ITEMS,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "JSON payload item count exceeds configured maximum."
                ),
                metadata={
                    "items": stats.items,
                    "max_items": policy.max_json_items,
                },
            )
        )

    return report.finish()


# ============================================================
# Environment and credential safety
# ============================================================

PUBLIC_ENV_NAMES: Final[tuple[str, ...]] = (
    "SUPABASE_URL",
    "OSGUIDE_RUN_MODE",
    "OSGUIDE_RUNTIME_MINUTES",
    "OSGUIDE_MAX_APPS",
)

SECRET_ENV_HINTS: Final[tuple[str, ...]] = (
    "SUPABASE_SERVICE_ROLE",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SECRET_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)


@dataclass(frozen=True, slots=True)
class CredentialPresence:
    name: str
    present: bool
    classification: SecretClass

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "present": self.present,
            "classification": self.classification.value,
        }


def credential_presence(
    name: str,
) -> CredentialPresence:
    safe_name = sanitize_text(
        name,
        max_length=200,
    )

    value = os.getenv(
        safe_name
    )

    classification = classify_secret(
        safe_name,
        value or "",
    )

    return CredentialPresence(
        name=safe_name,
        present=bool(
            value
        ),
        classification=classification,
    )


def environment_presence_summary(
    names: Iterable[str],
) -> dict[str, bool]:
    return {
        sanitize_text(
            name,
            max_length=200,
        ): bool(
            os.getenv(
                str(
                    name
                )
            )
        )
        for name in names
    }


def find_secret_named_fields(
    mapping: Mapping[str, object],
    *,
    prefix: str = "",
    max_results: int = 100,
) -> list[str]:
    output: list[
        str
    ] = []

    def walk(
        value: object,
        path: str,
        depth: int,
    ) -> None:
        if len(
            output
        ) >= max_results:
            return

        if depth > 8:
            return

        if isinstance(
            value,
            Mapping,
        ):
            for key, item in value.items():
                key_text = sanitize_text(
                    key,
                    max_length=128,
                )

                current_path = (
                    f"{path}.{key_text}"
                    if path
                    else key_text
                )

                if is_secret_like(
                    key_text,
                    item,
                ):
                    output.append(
                        current_path
                    )

                walk(
                    item,
                    current_path,
                    depth + 1,
                )

        elif isinstance(
            value,
            Sequence,
        ) and not isinstance(
            value,
            (str, bytes, bytearray),
        ):
            for index, item in enumerate(
                value
            ):
                walk(
                    item,
                    f"{path}[{index}]",
                    depth + 1,
                )

    walk(
        mapping,
        prefix,
        0,
    )

    return output


# ============================================================
# Source-code secret heuristics
# ============================================================

SUSPICIOUS_ASSIGNMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?ix)
    \b(
        [A-Za-z_][A-Za-z0-9_-]*
        (?:
            api[_-]?key|
            secret|
            token|
            password|
            service[_-]?role|
            authorization
        )
        [A-Za-z0-9_-]*
    )\b
    \s*[:=]\s*
    ["']
    ([^"']{12,})
    ["']
    """
)

DYNAMIC_CODE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:eval|exec|compile)\s*\("
)

SUSPICIOUS_SHELL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:"
    r"\bcurl\b.*\|\s*(?:sh|bash)\b|"
    r"\bwget\b.*\|\s*(?:sh|bash)\b|"
    r"\brm\s+-rf\s+/|"
    r"\bchmod\s+777\b"
    r")"
)


def scan_text_for_embedded_secrets(
    text: str,
    *,
    subject: str | None = None,
) -> SecurityReport:
    report = SecurityReport()

    for match in SUSPICIOUS_ASSIGNMENT_RE.finditer(
        text
    ):
        variable_name = sanitize_text(
            match.group(
                1
            ),
            max_length=100,
        )

        report.add(
            SecurityFinding(
                code=SecurityFindingCode.EMBEDDED_SECRET,
                severity=SecuritySeverity.CRITICAL,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Possible hard-coded secret assignment detected."
                ),
                subject=subject,
                metadata={
                    "field": variable_name,
                    "value": "[REDACTED]",
                },
            )
        )

    if DYNAMIC_CODE_RE.search(
        text
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.DYNAMIC_CODE_FORBIDDEN,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.BLOCK,
                message=(
                    "Dynamic code execution construct detected."
                ),
                subject=subject,
            )
        )

    if SUSPICIOUS_SHELL_RE.search(
        text
    ):
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.SHELL_PAYLOAD_SUSPICIOUS,
                severity=SecuritySeverity.HIGH,
                disposition=SecurityDisposition.REVIEW,
                message=(
                    "Potentially dangerous shell pattern detected."
                ),
                subject=subject,
            )
        )

    return report.finish()


def scan_file_for_embedded_secrets(
    path: str | Path,
    *,
    max_bytes: int = 2_000_000,
) -> SecurityReport:
    target = Path(
        path
    )

    report = SecurityReport()

    try:
        raw = target.read_bytes()
    except OSError:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.POLICY_VIOLATION,
                severity=SecuritySeverity.MEDIUM,
                disposition=SecurityDisposition.REVIEW,
                message="File could not be read for security scan.",
                subject=str(
                    target
                ),
            )
        )

        return report.finish()

    if len(
        raw
    ) > max_bytes:
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.RESPONSE_TOO_LARGE,
                severity=SecuritySeverity.MEDIUM,
                disposition=SecurityDisposition.REVIEW,
                message=(
                    "File exceeds security scanner size limit."
                ),
                subject=str(
                    target
                ),
            )
        )

        return report.finish()

    try:
        text = raw.decode(
            "utf-8"
        )
    except UnicodeDecodeError:
        return report.finish()

    scanned = scan_text_for_embedded_secrets(
        text,
        subject=str(
            target
        ),
    )

    report.findings.extend(
        scanned.findings
    )

    return report.finish()


# ============================================================
# Repository security scan
# ============================================================

DEFAULT_CODE_SUFFIXES: Final[tuple[str, ...]] = (
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".env",
    ".txt",
)

DEFAULT_SKIP_DIRECTORIES: Final[tuple[str, ...]] = (
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
)


def scan_repository_tree(
    root: str | Path,
    *,
    suffixes: Sequence[str] = DEFAULT_CODE_SUFFIXES,
    skip_directories: Sequence[str] = DEFAULT_SKIP_DIRECTORIES,
    max_files: int = 1_000,
    max_file_bytes: int = 2_000_000,
) -> SecurityReport:
    report = SecurityReport()

    root_path = Path(
        root
    )

    if not root_path.exists():
        report.add(
            SecurityFinding(
                code=SecurityFindingCode.POLICY_VIOLATION,
                severity=SecuritySeverity.MEDIUM,
                disposition=SecurityDisposition.REVIEW,
                message="Repository scan root does not exist.",
                subject=str(
                    root_path
                ),
            )
        )

        return report.finish()

    normalized_suffixes = {
        suffix.lower()
        for suffix in suffixes
    }

    skip = {
        name
        for name in skip_directories
    }

    scanned_files = 0

    for path in root_path.rglob(
        "*"
    ):
        if scanned_files >= max_files:
            report.add(
                SecurityFinding(
                    code=SecurityFindingCode.POLICY_VIOLATION,
                    severity=SecuritySeverity.MEDIUM,
                    disposition=SecurityDisposition.REVIEW,
                    message=(
                        "Repository scan reached configured file limit."
                    ),
                    metadata={
                        "max_files": max_files,
                    },
                )
            )
            break

        if not path.is_file():
            continue

        if any(
            part in skip
            for part in path.parts
        ):
            continue

        if path.suffix.lower() not in normalized_suffixes:
            continue

        scanned_files += 1

        child_report = scan_file_for_embedded_secrets(
            path,
            max_bytes=max_file_bytes,
        )

        report.findings.extend(
            child_report.findings
        )

    return report.finish()


# ============================================================
# Security guard orchestration
# ============================================================

@dataclass(slots=True)
class SecurityGuard:
    policy: SecurityPolicy = field(
        default_factory=SecurityPolicy
    )

    def __post_init__(
        self,
    ) -> None:
        self.policy.validate()

    def package_id(
        self,
        value: object,
    ) -> SecurityReport:
        return validate_package_id(
            value
        )

    def url(
        self,
        value: object,
        *,
        purpose: URLPurpose = URLPurpose.GENERIC,
        resolve_dns: bool | None = None,
    ) -> SecurityReport:
        return validate_url(
            value,
            purpose=purpose,
            policy=self.policy,
            resolve_dns=resolve_dns,
        )

    def github_url(
        self,
        value: object,
        *,
        resolve_dns: bool | None = None,
    ) -> SecurityReport:
        return validate_github_url(
            value,
            policy=self.policy,
            resolve_dns=resolve_dns,
        )

    def fdroid_url(
        self,
        value: object,
        *,
        resolve_dns: bool | None = None,
    ) -> SecurityReport:
        return validate_fdroid_url(
            value,
            policy=self.policy,
            resolve_dns=resolve_dns,
        )

    def apk_url(
        self,
        value: object,
        *,
        resolve_dns: bool | None = None,
    ) -> SecurityReport:
        return validate_apk_url(
            value,
            policy=self.policy,
            resolve_dns=resolve_dns,
        )

    def supabase_url(
        self,
        value: object,
        *,
        resolve_dns: bool | None = None,
    ) -> SecurityReport:
        return validate_supabase_url(
            value,
            policy=self.policy,
            resolve_dns=resolve_dns,
        )

    def redirect(
        self,
        value: object,
        *,
        purpose: URLPurpose,
        redirect_index: int,
        resolve_dns: bool | None = None,
    ) -> RedirectDecision:
        return validate_redirect_target(
            value,
            purpose=purpose,
            redirect_index=redirect_index,
            policy=self.policy,
            resolve_dns=resolve_dns,
        )

    def apk_content_type(
        self,
        value: object,
    ) -> SecurityReport:
        return validate_apk_content_type(
            value
        )

    def json_content_type(
        self,
        value: object,
    ) -> SecurityReport:
        return validate_json_content_type(
            value
        )

    def response_size(
        self,
        content_length: int | None,
    ) -> SecurityReport:
        return validate_response_size(
            content_length,
            max_bytes=self.policy.max_download_bytes,
        )

    def sha256(
        self,
        value: object,
    ) -> SecurityReport:
        return validate_sha256(
            value
        )

    def filename(
        self,
        value: object,
    ) -> SecurityReport:
        return validate_filename(
            value
        )

    def relative_path(
        self,
        value: object,
    ) -> SecurityReport:
        return validate_relative_path(
            value
        )

    def json_payload(
        self,
        raw: str | bytes,
    ) -> SecurityReport:
        return validate_json_payload(
            raw,
            policy=self.policy,
        )


# ============================================================
# Merge reports
# ============================================================

def merge_security_reports(
    reports: Iterable[
        SecurityReport
    ],
) -> SecurityReport:
    combined = SecurityReport()

    for report in reports:
        combined.findings.extend(
            report.findings
        )

    return combined.finish()


# ============================================================
# Fail-closed helpers
# ============================================================

def require_allowed(
    report: SecurityReport,
    *,
    context: str = "security check",
) -> None:
    if report.blocked:
        codes = sorted(
            {
                finding.code.value
                for finding in report.findings
                if finding.disposition
                == SecurityDisposition.BLOCK
            }
        )

        raise PermissionError(
            f"{context} blocked: {', '.join(codes)}"
        )


def require_no_review(
    report: SecurityReport,
    *,
    context: str = "security check",
) -> None:
    require_allowed(
        report,
        context=context,
    )

    if report.review_required:
        codes = sorted(
            {
                finding.code.value
                for finding in report.findings
                if finding.disposition
                == SecurityDisposition.REVIEW
            }
        )

        raise PermissionError(
            f"{context} requires review: {', '.join(codes)}"
        )


# ============================================================
# Diagnostic helpers
# ============================================================

def run_security_diagnostic() -> dict[str, object]:
    policy = SecurityPolicy(
        resolve_dns_before_network=False
    )

    guard = SecurityGuard(
        policy=policy
    )

    package_report = guard.package_id(
        "org.osguide.diagnostic"
    )

    private_url_report = guard.url(
        "https://127.0.0.1/internal",
        purpose=URLPurpose.GENERIC,
        resolve_dns=False,
    )

    github_report = guard.github_url(
        "https://github.com/example/project",
        resolve_dns=False,
    )

    malicious_github_report = guard.github_url(
        "https://github.com.attacker.example/project",
        resolve_dns=False,
    )

    supabase_report = guard.supabase_url(
        "https://example.supabase.co",
        resolve_dns=False,
    )

    secret_scan = scan_text_for_embedded_secrets(
        'SUPABASE_SERVICE_ROLE_KEY = "abcdefghijklmnopqrstuvwxyz0123456789SECRET"'
    )

    traversal_report = guard.relative_path(
        "../../etc/passwd"
    )

    sha_report = guard.sha256(
        "a" * 64
    )

    json_report = guard.json_payload(
        '{"ok": true, "items": [1, 2, 3]}'
    )

    return {
        "component": SECURITY_COMPONENT,
        "schema_version": SECURITY_SCHEMA_VERSION,
        "package_id_allowed": not package_report.blocked,
        "private_url_blocked": private_url_report.blocked,
        "github_allowed": not github_report.blocked,
        "fake_github_blocked": malicious_github_report.blocked,
        "supabase_allowed": not supabase_report.blocked,
        "embedded_secret_blocked": secret_scan.blocked,
        "traversal_blocked": traversal_report.blocked,
        "sha256_allowed": not sha_report.blocked,
        "json_allowed": not json_report.blocked,
    }


def run_redaction_diagnostic() -> dict[str, object]:
    raw = {
        "package_id": "org.osguide.example",
        "source_url": "https://github.com/example/project",
        "api_key": "top-secret-value",
        "nested": {
            "authorization": "Bearer test-value",
            "normal": "visible",
        },
    }

    return safe_mapping(
        raw
    )


def run_url_diagnostic() -> dict[str, object]:
    policy = SecurityPolicy(
        resolve_dns_before_network=False
    )

    test_cases = {
        "good_github": (
            "https://github.com/owner/repo",
            URLPurpose.GITHUB,
        ),
        "fake_github": (
            "https://github.com.attacker.invalid/repo",
            URLPurpose.GITHUB,
        ),
        "loopback": (
            "https://127.0.0.1/",
            URLPurpose.GENERIC,
        ),
        "userinfo": (
            "https://user:pass@example.org/",
            URLPurpose.GENERIC,
        ),
        "bad_port": (
            "https://example.org:8443/",
            URLPurpose.GENERIC,
        ),
        "fdroid": (
            "https://f-droid.org/packages/org.fdroid.fdroid/",
            URLPurpose.FDROID,
        ),
    }

    output: dict[
        str,
        object,
    ] = {}

    for name, (
        url,
        purpose,
    ) in test_cases.items():
        report = validate_url(
            url,
            purpose=purpose,
            policy=policy,
            resolve_dns=False,
        )

        output[
            name
        ] = {
            "blocked": report.blocked,
            "review_required": report.review_required,
            "codes": [
                finding.code.value
                for finding in report.findings
            ],
        }

    return output


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "CredentialPresence",
    "DEFAULT_ALLOWED_PORTS",
    "DEFAULT_ALLOWED_SCHEMES",
    "DEFAULT_APK_CONTENT_TYPES",
    "DEFAULT_BLOCKED_HOSTS",
    "DEFAULT_DNS_TIMEOUT_SECONDS",
    "DEFAULT_FDROID_HOSTS",
    "DEFAULT_GITHUB_HOSTS",
    "DEFAULT_JSON_CONTENT_TYPES",
    "DEFAULT_MAX_DOWNLOAD_BYTES",
    "DEFAULT_MAX_FILENAME_LENGTH",
    "DEFAULT_MAX_JSON_BYTES",
    "DEFAULT_MAX_JSON_DEPTH",
    "DEFAULT_MAX_JSON_ITEMS",
    "DEFAULT_MAX_REDIRECTS",
    "DEFAULT_MAX_TEXT_LENGTH",
    "DEFAULT_MAX_URL_LENGTH",
    "DEFAULT_SUPABASE_SUFFIXES",
    "JsonStructureStats",
    "PUBLIC_ENV_NAMES",
    "RedirectDecision",
    "SECURITY_COMPONENT",
    "SECURITY_SCHEMA_VERSION",
    "SECRET_ENV_HINTS",
    "SecretClass",
    "SecurityDisposition",
    "SecurityFinding",
    "SecurityFindingCode",
    "SecurityGuard",
    "SecurityPolicy",
    "SecurityReport",
    "SecuritySeverity",
    "URLPurpose",
    "canonicalize_url",
    "checksum_matches",
    "classify_secret",
    "contains_control_characters",
    "credential_presence",
    "environment_presence_summary",
    "find_secret_named_fields",
    "has_path_traversal",
    "hostname_matches",
    "hostname_matches_any",
    "hostname_matches_suffix",
    "is_forbidden_ip",
    "is_safe_filename",
    "is_secret_like",
    "is_valid_hostname",
    "is_valid_package_id",
    "is_valid_sha256",
    "literal_ip_from_hostname",
    "measure_json_structure",
    "merge_security_reports",
    "normalize_filename",
    "normalize_hostname",
    "normalize_package_id",
    "normalize_sha256",
    "normalize_unicode_text",
    "normalize_url",
    "normalized_content_type",
    "parsed_url",
    "require_allowed",
    "require_no_review",
    "resolve_hostname_ips",
    "run_redaction_diagnostic",
    "run_security_diagnostic",
    "run_url_diagnostic",
    "safe_join",
    "safe_json_loads",
    "safe_mapping",
    "safe_value",
    "sanitize_text",
    "scan_file_for_embedded_secrets",
    "scan_repository_tree",
    "scan_text_for_embedded_secrets",
    "sha256_bytes",
    "sha256_file",
    "utc_now",
    "validate_apk_content_type",
    "validate_apk_url",
    "validate_content_type",
    "validate_fdroid_url",
    "validate_filename",
    "validate_github_url",
    "validate_json_content_type",
    "validate_json_payload",
    "validate_package_id",
    "validate_redirect_target",
    "validate_relative_path",
    "validate_response_size",
    "validate_sha256",
    "validate_supabase_url",
    "validate_url",
)
