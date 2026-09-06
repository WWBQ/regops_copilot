"""日志脱敏：身份证、手机号、账号。"""

from __future__ import annotations

import re

_ID_CARD = re.compile(r"\b\d{17}[\dXx]\b")
_PHONE = re.compile(r"\b1[3-9]\d{9}\b")
_ACCOUNT = re.compile(r"\b\d{12,19}\b")


def mask_pii(text: str) -> str:
    masked = _ID_CARD.sub("[身份证]", text)
    masked = _PHONE.sub("[手机号]", masked)
    return _ACCOUNT.sub("[账号]", masked)
