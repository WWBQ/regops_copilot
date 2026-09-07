"""W6-3 数字抽取与证据回溯。"""

from app.agents.evidence import (
    INTERCEPT_PREFIX,
    REDACT_TOKEN,
    apply_checked_reply,
    check_reply,
    extract_claims,
    pack_from_facts_and_snippets,
)


def test_extract_skips_year_page_mark_and_hours():
    claims = extract_claims("2024 年年报第 20 页已引用 [1]，默认 24 小时，覆盖 5 家。")
    assert claims == []


def test_extract_amount_and_percent():
    claims = extract_claims("净利润约 415.88 亿元，同比 10.91%。")
    kinds = {(item.kind, item.unit) for item in claims}
    assert ("amount", "亿元") in kinds
    assert ("percent", "%") in kinds


def test_grounded_yi_matches_fact():
    pack = pack_from_facts_and_snippets(["41587940000"], [])
    result = check_reply("净利润约 415.88 亿元。", pack)
    assert result.ok
    assert result.claims[0].status == "fact"


def test_unbacked_amount_is_redacted():
    pack = pack_from_facts_and_snippets(["777102455000"], ["管理层讨论销量。"])
    result = check_reply("研发投入约 542 亿元。", pack)
    assert not result.ok
    assert result.claims[0].status == "unbacked"
    assert INTERCEPT_PREFIX in result.reply
    assert REDACT_TOKEN in result.reply
    assert "542" not in result.reply.split("\n\n", 1)[-1]


def test_unit_error_wan_vs_yi():
    pack = pack_from_facts_and_snippets(["41587940000"], [])
    result = check_reply("净利润约 415.88 万元。", pack)
    assert not result.ok
    assert result.claims[0].status == "unit_error"


def test_percent_scale_blocks_decimal():
    pack = pack_from_facts_and_snippets([], ["净利润同比变动 10.91%。"])
    result = check_reply("同比变动 0.1091。", pack)
    assert not result.ok
    assert result.claims[0].status == "percent_scale"


def test_computed_delta_is_blocked():
    pack = pack_from_facts_and_snippets(["41587940000", "12660012515.78"], [])
    result = check_reply("两家差额约 289.28 亿元。", pack)
    assert not result.ok
    assert result.claims[0].status == "computed"


def test_citation_percent_is_allowed():
    pack = pack_from_facts_and_snippets([], ["报告期内净利润同比变动 10.91%。"])
    result = check_reply("年报称同比变动 10.91%。", pack)
    assert result.ok
    assert result.claims[0].status == "citation"


def test_mixed_reply_keeps_grounded_and_redacts_unbacked():
    pack = pack_from_facts_and_snippets(["41587940000"], [])
    result = check_reply("净利润约 415.88 亿元，研发投入约 542 亿元。", pack)
    assert not result.ok
    statuses = {item.status for item in result.claims}
    assert "fact" in statuses
    assert "unbacked" in statuses
    assert "415.88" in result.reply
    assert "542" not in result.reply.split("\n\n", 1)[-1]


def test_apply_checked_reply_maps_rag_route():
    pack = pack_from_facts_and_snippets([], [])
    reply, route, checked = apply_checked_reply("营收 999 亿元。", pack, route="rag")
    assert not checked.ok
    assert route == "rag_blocked"
    assert INTERCEPT_PREFIX in reply


def test_stock_code_not_treated_as_amount():
    claims = extract_claims("样本公司 002594，没有编造金额。")
    assert claims == []


def test_draft_uuid_not_treated_as_amount():
    claims = extract_claims("已写入 PENDING 审查工单 `11111111-1111-1111-1111-111111111111`。")
    assert claims == []


def test_patent_counts_and_yuan_in_rag_snippet():
    text = (
        "2024 年度，公司研发投入总额 104.46 亿元人民币，同比减少 5.33%。"
        "已累计申请专利 28,000 余项，授权专利 17,000 余项。"
    )
    kinds = {(item.kind, item.unit, str(item.mantissa)) for item in extract_claims(text)}
    assert ("amount", "亿元", "104.46") in kinds
    assert ("percent", "%", "5.33") in kinds
    assert all("28000" not in str(item.mantissa) and "17000" not in str(item.mantissa) for item in extract_claims(text))
    pack = pack_from_facts_and_snippets(["41587940000"], [text])
    result = check_reply(
        "净利润约 415.88 亿元。管理层：" + text,
        pack,
    )
    assert result.ok

