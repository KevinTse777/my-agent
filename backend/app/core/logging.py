import logging
import re


_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*")
_JWT_RE = re.compile(r"\b[A-Za-z0-9\-_]{12,}\.[A-Za-z0-9\-_]{12,}\.[A-Za-z0-9\-_]{12,}\b")
_KEY_VALUE_PATTERNS = [
    re.compile(r'(?i)("password"\s*:\s*")([^"]*)(")'),
    re.compile(r"(?i)(password=)([^\s,]+)"),
    re.compile(r'(?i)("access_token"\s*:\s*")([^"]*)(")'),
    re.compile(r"(?i)(access_token=)([^\s,]+)"),
    re.compile(r'(?i)("refresh_token"\s*:\s*")([^"]*)(")'),
    re.compile(r"(?i)(refresh_token=)([^\s,]+)"),
    re.compile(r'(?i)("authorization"\s*:\s*")([^"]*)(")'),
    re.compile(r"(?i)(authorization=\s*bearer\s+)([^\s,]+)"),
    re.compile(r"(?i)(authorization=)([^\s,]+)"),
]


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern in _KEY_VALUE_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]\3", redacted) if pattern.groups >= 3 else pattern.sub(r"\1[REDACTED]", redacted)

    redacted = _BEARER_RE.sub("Bearer [REDACTED]", redacted)
    redacted = _JWT_RE.sub("[REDACTED_TOKEN]", redacted)
    redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_sensitive_text(formatted)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
