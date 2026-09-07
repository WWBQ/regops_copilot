"""多步审查任务入口：两家以上 +（结论 / 管理层 / 叙述），才进图。"""

from __future__ import annotations

import re
from typing import Literal

from app.asknum.slots import is_unsupported_ratio, parse_slots

# 纯「对比两家营收多少」仍走问数；只有要解释/结论才拉图
_REVIEW_TASK_RE = re.compile(
    r"管理层|讨论与分析|md\s*&?\s*a|"
    r"给出结论|出具结论|合规结论|审查结论|审查意见|"
    r"解释差异|差异原因|"
    r"核对.{0,12}结论|对比.{0,24}结论|对比.{0,24}解释|结合.{0,16}对比",
    re.IGNORECASE,
)

# 用户点名「你来选工具」才进 Function Calling；单问营收 / 两家结论不走这里
_TOOL_LOOP_RE = re.compile(
    r"自己(?:决定|判断|选)(?:调用)?(?:哪些)?工具|"
    r"你来选工具|"
    r"按需调用工具|"
    r"用工具(?:帮我|查|检索)|"
    r"工具自选|"
    r"先(?:看|列)(?:看)?能查什么",
    re.IGNORECASE,
)

# 制度/车型等仍走 RAG，不进工具循环
_RAG_KEEP_RE = re.compile(
    r"风险因素|内控|战略|展望|车型|新车|新品|"
    r"是否违规|是否合规|处罚|条款"
)

_OVERVIEW_RE = re.compile(
    r"(?:经营|业绩|财务)(?:得?怎么样|如何|情况|状况)|"
    r"整体(?:情况|怎么样)|"
    r"(?:今年|本年|这?一年|\d{4}年?)怎么样|"
    r"好不好|"
    r"有哪些可查|能查什么|可查指标|库里有什么"
)

_UNSUPPORTED_TOPIC_RE = re.compile(
    r"分红|股利|股息|派息",
)

_BLOCKED_FOLLOWUP_RE = re.compile(
    r"能不能用|到底能不能|能否采用|能否使用|可不可以用|能不能信|"
    r"待复核|质量门|口径|"
    r"为什么(?:不能用|查不到|没有|待复核|被拦)|"
    r"有什么问题"
)


def wants_review_graph(question: str) -> bool:
    slots = parse_slots(question)
    if len(slots.company_codes) < 2:
        return False
    if _REVIEW_TASK_RE.search(question):
        return True
    return bool(slots.narrative)


def _unsupported_topic(question: str) -> bool:
    return is_unsupported_ratio(question) or bool(_UNSUPPORTED_TOPIC_RE.search(question or ""))


def tool_loop_reason(question: str) -> str | None:
    """返回进工具循环的原因；None 表示不进。两家+结论由 wants_review_graph 先拦。"""
    text = question or ""
    if _TOOL_LOOP_RE.search(text):
        return "opt_in"
    slots = parse_slots(text)
    if not slots.company_codes:
        return None
    if _RAG_KEEP_RE.search(text):
        return None
    if _unsupported_topic(text):
        return "unsupported_topic"
    if slots.concepts and _BLOCKED_FOLLOWUP_RE.search(text):
        return "blocked_followup"
    if (
        not slots.concepts
        and _OVERVIEW_RE.search(text)
        and not re.search(r"数字多少|财务数字", text)
    ):
        return "overview"
    return None


_RESUME_RE = re.compile(
    r"^(?:继续|确认|同意|好的|可以|生成结论|确认生成(?:结论)?|ok|yes)\s*[。.!！]?$",
    re.IGNORECASE,
)
_CANCEL_RE = re.compile(
    r"^(?:取消|停止|不要|放弃|算了|no)\s*[。.!！]?$",
    re.IGNORECASE,
)


def checkpoint_command(question: str) -> Literal["resume", "cancel"] | None:
    text = (question or "").strip()
    if _CANCEL_RE.match(text):
        return "cancel"
    if _RESUME_RE.match(text):
        return "resume"
    return None


def wants_tool_loop(question: str) -> bool:
    return tool_loop_reason(question) is not None
