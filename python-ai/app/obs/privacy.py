"""日志 / Trace 脱敏：身份证、手机号、账号、API Key。"""

from __future__ import annotations

import re

_ID_CARD = re.compile(r"\b\d{17}[\dXx]\b")
_PHONE = re.compile(r"\b1[3-9]\d{9}\b")
_ACCOUNT = re.compile(r"\b\d{12,19}\b")
_API_KEY = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._\-+=/]{8,})\b"
)
_ENV_SECRET = re.compile(
    r"(?i)\b(?:DEEPSEEK_API_KEY|QWEN_API_KEY|REGOPS_JWT_SECRET|REGOPS_SERVICE_TOKEN"
    r"|LANGFUSE_SECRET_KEY|LANGFUSE_PUBLIC_KEY)\s*[=:]\s*\S+"
)


def mask_pii(text: str) -> str:
    masked = _ID_CARD.sub("[身份证]", text)
    masked = _PHONE.sub("[手机号]", masked)
    return _ACCOUNT.sub("[账号]", masked)


def mask_secrets(text: str) -> str:
    masked = _API_KEY.sub("[密钥]", text)
    return _ENV_SECRET.sub("[密钥]", masked)


def mask_for_log(text: str) -> str:
    return mask_secrets(mask_pii(text))
