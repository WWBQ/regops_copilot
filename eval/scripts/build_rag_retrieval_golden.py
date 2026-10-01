#!/usr/bin/env python3
"""从 doc_chunks 探测 gold page，生成 eval/golden/rag_retrieval_100.json。

用法（项目根目录）：
  cd python-ai && .venv/bin/python ../eval/scripts/build_rag_retrieval_golden.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python-ai"))

from app.db.connection import get_connection  # noqa: E402

OUT_PATH = ROOT / "eval" / "golden" / "rag_retrieval_100.json"

COMPANY_NAMES = {
    "002594_2024": ("002594", "比亚迪"),
    "601633_2024": ("601633", "长城汽车"),
    "000333_2024": ("000333", "美的集团"),
    "000651_2024": ("000651", "格力电器"),
    "600031_2024": ("600031", "三一重工"),
}

# (category, question_template, probe_keywords, prefer_page_hint)
# probe_keywords: 用于在 chunk 中定位证据页；命中任一即可
ITEM_SPECS: list[tuple[str, str, list[str], str | None]] = [
    # ── 比亚迪 002594 ──
    ("numeric_financial", "比亚迪2024年营业收入是多少", ["营业收入", "营业总收入"], "主要会计数据"),
    ("numeric_financial", "比亚迪2024年归属于上市公司股东的净利润是多少", ["归属于上市公司股东的净利润"], None),
    ("numeric_financial", "比亚迪2024年末总资产是多少", ["总资产"], None),
    ("numeric_financial", "比亚迪2024年经营活动产生的现金流量净额是多少", ["经营活动产生的现金流量净额"], None),
    ("numeric_financial", "比亚迪2024年研发投入约为多少", ["研发投入", "542"], "董事长"),
    ("numeric_ratio", "比亚迪2024年汽车业务毛利率是多少", ["毛利率", "汽车"], None),
    ("numeric_ratio", "比亚迪2024年加权平均净资产收益率ROE是多少", ["加权平均净资产收益率"], None),
    ("product_enum", "比亚迪2024年推出了哪些新车型或新产品", ["全新车型", "正式上市", "元UP", "秦L"], None),
    ("product_enum", "比亚迪2024年新能源汽车销量是多少", ["新能源汽车销量", "销量"], None),
    ("segment_business", "比亚迪2024年境外收入占比或境外业务情况", ["境外", "海外"], None),
    ("segment_business", "比亚迪2024年分产品或分行业收入结构", ["分行业", "分产品"], None),
    ("compliance_risk", "比亚迪2024年内部控制评价报告结论", ["内部控制评价", "内部控制"], None),
    ("compliance_risk", "比亚迪年报第一节重要提示如何表述风险因素", ["第一节", "风险因素", "可能面临"], "第一节"),
    ("governance", "比亚迪2024年利润分配预案或分红方案", ["利润分配", "派发现金"], None),
    ("governance", "比亚迪2024年董事会成员有哪些", ["董事", "董事会成员"], None),
    ("esg_sustainability", "比亚迪2024年碳排放或温室气体排放披露", ["碳排放", "温室气体"], None),
    ("esg_sustainability", "比亚迪2024年绿色低碳或ESG方面有哪些举措", ["绿色", "ESG", "低碳"], None),
    ("strategy_outlook", "比亚迪2024年发展战略或经营计划", ["发展战略", "经营计划"], None),
    ("cross_year_compare", "比亚迪2024年营业收入同比增长率是多少", ["同比增长", "营业收入"], None),
    ("cross_year_compare", "比亚迪2024年研发投入同比增长情况", ["研发投入", "同比"], None),
    # ── 长城汽车 601633 ──
    ("numeric_financial", "长城汽车2024年营业收入是多少", ["营业收入"], None),
    ("numeric_financial", "长城汽车2024年归属于上市公司股东的净利润是多少", ["归属于上市公司股东的净利润", "归属于母公司"], None),
    ("numeric_financial", "长城汽车2024年研发费用是多少", ["研发费用", "研发支出"], None),
    ("numeric_financial", "长城汽车2024年经营活动现金流量净额是多少", ["经营活动产生的现金流量净额"], None),
    ("numeric_ratio", "长城汽车2024年海外业务毛利率变化", ["毛利率", "海外"], None),
    ("numeric_ratio", "长城汽车2024年销量或整车销量是多少", ["销量", "123.45"], None),
    ("product_enum", "2024年长城新推出的车型有哪些", ["新推出", "上市", "哈弗", "坦克"], None),
    ("product_enum", "长城灵魂S2000摩托车2024年何时发布", ["长城灵魂", "S2000"], None),
    ("segment_business", "长城汽车2024年海外销售多少万辆", ["海外", "45.41", "海外年销售"], None),
    ("segment_business", "长城汽车2024年SUV或越野业务情况", ["SUV", "越野"], None),
    ("compliance_risk", "长城汽车2024年内部控制自我评价", ["内部控制"], None),
    ("compliance_risk", "长城汽车2024年审计意见类型", ["审计报告", "审计意见"], None),
    ("governance", "长城汽车2024年每股派发现金红利多少", ["派发现金红利", "利润分配"], None),
    ("governance", "长城汽车2024年股权激励计划情况", ["股权激励"], None),
    ("esg_sustainability", "长城汽车2024年环保或碳中和相关披露", ["环保", "碳中和", "绿色"], None),
    ("esg_sustainability", "长城汽车2024年社会责任履行情况", ["社会责任"], None),
    ("strategy_outlook", "长城汽车2024年新能源战略或Hi4技术", ["新能源", "Hi4"], None),
    ("strategy_outlook", "长城汽车2024年全球化战略进展", ["全球化", "海外战略"], None),
    ("cross_year_compare", "长城汽车2024年海外销售同比增长", ["海外", "同比"], None),
    ("cross_year_compare", "长城汽车2024年净利润同比变动原因", ["净利润", "同比"], None),
    # ── 美的集团 000333 ──
    ("numeric_financial", "美的集团2024年营业总收入是多少", ["营业总收入", "营业收入"], None),
    ("numeric_financial", "美的集团2024年归属于上市公司股东的净利润是多少", ["归属于上市公司股东的净利润"], None),
    ("numeric_financial", "美的集团2024年末总资产是多少", ["总资产"], None),
    ("numeric_financial", "美的集团2024年经营活动现金流量净额是多少", ["经营活动产生的现金流量净额", "经营活动现金流量", "现金净流量"], "主要会计数据"),
    ("numeric_ratio", "美的集团2024年智能家居业务毛利率", ["毛利率", "智能家居"], None),
    ("numeric_ratio", "美的集团2024年加权平均净资产收益率", ["净资产收益率"], None),
    ("product_enum", "美的集团2024年发布了哪些新品或新技术", ["发布", "推出", "新品"], None),
    ("product_enum", "美的集团2024年COLMO或高端品牌情况", ["COLMO", "高端品牌"], None),
    ("segment_business", "美的集团2024年ToB业务或商业及工业板块", ["ToB", "商业及工业"], None),
    ("segment_business", "美的集团2024年海外收入占比", ["海外", "境外"], None),
    ("compliance_risk", "美的集团2024年内部控制评价结论", ["内部控制"], None),
    ("compliance_risk", "美的集团2024年重大诉讼或仲裁", ["诉讼", "仲裁"], None),
    ("governance", "美的集团2024年利润分配方案", ["利润分配", "分红"], None),
    ("governance", "美的集团2024年回购股份情况", ["回购"], None),
    ("esg_sustainability", "美的集团2024年节能降碳或绿色制造", ["节能", "降碳", "绿色制造"], None),
    ("esg_sustainability", "美的集团2024年员工培训或人才发展", ["员工培训", "人才"], None),
    ("strategy_outlook", "美的集团2024年数字化或智能化转型", ["数字化", "智能化"], None),
    ("strategy_outlook", "美的集团2024年全球化布局", ["全球化", "海外布局"], None),
    ("cross_year_compare", "美的集团2024年营业总收入同比增长", ["同比增长", "营业总收入"], None),
    ("cross_year_compare", "美的集团2024年净利润同比变动", ["净利润", "同比"], None),
    # ── 格力电器 000651 ──
    ("numeric_financial", "格力电器2024年营业收入是多少", ["营业收入"], None),
    ("numeric_financial", "格力电器2024年归属于上市公司股东的净利润是多少", ["归属于上市公司股东的净利润", "归属于母公司所有者的净利润", "净利润"], "主要会计数据"),
    ("numeric_financial", "格力电器2024年经营活动现金流量净额是多少", ["经营活动产生的现金流量净额"], None),
    ("numeric_financial", "格力电器2024年研发投入是多少", ["研发投入", "研发支出"], None),
    ("numeric_ratio", "格力电器2024年空调业务或家用空调收入", ["空调", "家用空调"], None),
    ("numeric_ratio", "格力电器2024年资产负债率是多少", ["资产负债率", "资产负债", "负债合计", "资产总计"], "资产负债表"),
    ("product_enum", "格力电器2024年推出了哪些新产品", ["推出", "发布", "新品"], None),
    ("product_enum", "格力电器2024年工业制品或装备业务", ["工业制品", "装备"], None),
    ("segment_business", "格力电器2024年分产品收入构成", ["分产品", "分行业", "消费领域", "空调"], "管理层讨论"),
    ("segment_business", "格力电器2024年国内外销售比例", ["境内", "境外", "国内", "国外"], None),
    ("compliance_risk", "格力电器2024年内部控制评价", ["内部控制"], None),
    ("compliance_risk", "格力电器2024年关联交易披露", ["关联交易"], None),
    ("governance", "格力电器2024年分红派息方案", ["利润分配", "派息", "分红"], None),
    ("governance", "格力电器2024年股份回购进展", ["回购"], None),
    ("esg_sustainability", "格力电器2024年绿色制造或节能产品", ["绿色", "节能"], None),
    ("esg_sustainability", "格力电器2024年公益慈善或社会责任", ["公益", "社会责任"], None),
    ("strategy_outlook", "格力电器2024年多元化或工业领域战略", ["多元化", "工业"], None),
    ("strategy_outlook", "格力电器2024年渠道变革或数字化营销", ["渠道", "数字化"], None),
    ("cross_year_compare", "格力电器2024年营业收入同比变化", ["营业收入", "同比"], None),
    ("cross_year_compare", "格力电器2024年净利润同比变化", ["净利润", "同比"], None),
    # ── 三一重工 600031 ──
    ("numeric_financial", "三一重工2024年营业收入是多少", ["营业收入"], None),
    ("numeric_financial", "三一重工2024年归属于上市公司股东的净利润是多少", ["归属于上市公司股东的净利润", "净利润"], "主要会计数据"),
    ("numeric_financial", "三一重工2024年总资产是多少", ["总资产"], None),
    ("numeric_financial", "三一重工2024年研发费用是多少", ["研发费用", "研发支出"], None),
    ("numeric_ratio", "三一重工2024年挖掘机市占率或销量", ["挖掘机", "市占率", "销量"], None),
    ("numeric_ratio", "三一重工2024年海外主营业务毛利率", ["毛利率", "海外"], None),
    ("product_enum", "三一重工2024年推出了哪些新机型或新产品", ["推出", "发布", "新品"], None),
    ("product_enum", "三一重工2024年电动化或新能源产品", ["电动", "新能源"], None),
    ("segment_business", "三一重工2024年海外收入或国际化进展", ["海外", "国际化"], None),
    ("segment_business", "三一重工2024年混凝土机械业务情况", ["混凝土"], None),
    ("compliance_risk", "三一重工2024年内部控制评价", ["内部控制"], None),
    ("compliance_risk", "三一重工2024年重大风险提示", ["风险"], None),
    ("governance", "三一重工2024年利润分配预案", ["利润分配", "分红"], None),
    ("governance", "三一重工2024年董事及高管情况", ["董事", "高级管理人员"], None),
    ("esg_sustainability", "三一重工2024年安全生产或职业健康", ["安全生产", "职业健康"], None),
    ("esg_sustainability", "三一重工2024年绿色制造或减排", ["绿色", "减排", "碳"], None),
    ("strategy_outlook", "三一重工2024年全球化或国际化战略", ["全球化", "国际化"], None),
    ("strategy_outlook", "三一重工2024年数字化转型", ["数字化", "智能"], None),
    ("cross_year_compare", "三一重工2024年营业收入同比增长", ["营业收入", "同比"], None),
    ("cross_year_compare", "三一重工2024年海外销售增长", ["海外", "同比", "增长"], None),
]


# 个别 chunk 分词/OCR 导致自动探测失败时的手工 gold page（需对照 PDF 抽检）
MANUAL_GOLD_PAGES: dict[str, list[int]] = {
    "比亚迪2024年推出了哪些新车型或新产品": [16, 17, 18, 19, 20],
    "比亚迪2024年新能源汽车销量是多少": [3, 15, 49, 2, 13],
    "美的集团2024年经营活动现金流量净额是多少": [9, 53],
    "美的集团2024年归属于上市公司股东的净利润是多少": [10],
    "美的集团2024年发布了哪些新品或新技术": [41, 23, 27, 37, 39],
    "美的集团2024年COLMO或高端品牌情况": [33, 47, 63, 16, 21],
    "格力电器2024年归属于上市公司股东的净利润是多少": [7, 13],
    "格力电器2024年资产负债率是多少": [106, 117],
    "格力电器2024年分产品收入构成": [10, 25],
    "格力电器2024年推出了哪些新产品": [12, 14, 15, 22, 23, 24],
    "格力电器2024年工业制品或装备业务": [43, 235, 10, 12, 22],
    "三一重工2024年归属于上市公司股东的净利润是多少": [5, 6],
    "三一重工2024年推出了哪些新机型或新产品": [11, 12, 14, 15, 57],
    "三一重工2024年电动化或新能源产品": [8, 11, 12, 29, 13],
    "2024年长城新推出的车型有哪些": [21, 22, 23],
    "长城灵魂S2000摩托车2024年何时发布": [20, 23],
    # p5=第一节重要提示（声明无严重风险+指向第三节 13/22/42）；问句已对齐第一节，不另占 100 题槽位
    "比亚迪年报第一节重要提示如何表述风险因素": [5],
}


def probe_pages(doc_id: str, keywords: list[str], prefer_hint: str | None, limit: int = 5) -> list[int]:
    conditions = " OR ".join(["content ILIKE %s"] * len(keywords))
    section_conditions = " OR ".join(["COALESCE(metadata->>'section_title','') ILIKE %s"] * len(keywords))
    like_params = [f"%{kw}%" for kw in keywords]
    params: list[object] = [doc_id, *like_params, *like_params]
    sql = f"""
        SELECT DISTINCT (metadata->>'page')::int AS page,
               content,
               COALESCE(metadata->>'section_title','') AS section_title,
               COALESCE(metadata->>'clause_no','') AS clause_no
        FROM doc_chunks
        WHERE doc_id = %s AND (({conditions}) OR ({section_conditions}))
        ORDER BY page
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    if not rows:
        return []

    scored: list[tuple[int, int, int]] = []
    for page, content, section_title, clause_no in rows:
        if page is None:
            continue
        text = content or ""
        title = section_title or ""
        clause = clause_no or ""
        score = sum(1 for kw in keywords if kw in text)
        score += sum(2 for kw in keywords if kw in title or kw in clause)
        if prefer_hint and (prefer_hint in text or prefer_hint in title or prefer_hint in clause):
            score += 3
        # 目录页、页眉块容易被「第一节」之类词误中
        if text.strip().startswith("目录") or "目录" in text[:40]:
            score -= 4
        if "年度报告全文" in text and len(text) < 80:
            score -= 3
        if len(text) < 80:
            score -= 1
        scored.append((score, page, len(text)))

    scored.sort(key=lambda x: (-x[0], x[1]))
    pages: list[int] = []
    for _, page, _ in scored:
        if page not in pages:
            pages.append(page)
        if len(pages) >= limit:
            break
    return pages


def infer_doc_id(question: str) -> str:
    alias_map = {
        "比亚迪": "002594_2024",
        "长城汽车": "601633_2024",
        "长城": "601633_2024",
        "美的集团": "000333_2024",
        "美的": "000333_2024",
        "格力电器": "000651_2024",
        "格力": "000651_2024",
        "三一重工": "600031_2024",
        "三一": "600031_2024",
        "长城灵魂": "601633_2024",
    }
    for alias, doc_id in sorted(alias_map.items(), key=lambda x: -len(x[0])):
        if alias in question:
            return doc_id
    for doc_id, (_, name) in COMPANY_NAMES.items():
        if name in question:
            return doc_id
    code_match = re.search(r"\b(\d{6})\b", question)
    if code_match:
        code = code_match.group(1)
        for doc_id, (company_code, _) in COMPANY_NAMES.items():
            if company_code == code:
                return doc_id
    raise ValueError(f"cannot infer doc_id for question: {question}")


def build_items() -> list[dict]:
    items: list[dict] = []
    for index, (category, question, keywords, prefer) in enumerate(ITEM_SPECS, start=1):
        doc_id = infer_doc_id(question)
        company_code, company_name = COMPANY_NAMES[doc_id]
        gold_pages = MANUAL_GOLD_PAGES.get(question) or probe_pages(doc_id, keywords, prefer)
        if not gold_pages:
            # 回退：用第一个关键词单独搜
            gold_pages = probe_pages(doc_id, [keywords[0]], prefer)

        items.append(
            {
                "id": f"rag-{index:03d}",
                "category": category,
                "question": question,
                "doc_id": doc_id,
                "company_code": company_code,
                "company_name": company_name,
                "report_year": 2024,
                "gold_pages": gold_pages,
                "probe_keywords": keywords,
                "grading": "page_hit_at_k",
                "k": 12,
                "evidence_hint": prefer or keywords[0],
                "why_clean": f"2024年报已入库 doc_id={doc_id}；gold page 由 doc_chunks 关键词探测",
            }
        )
    return items


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="探测 gold_pages 并生成 / 对照 rag_retrieval_100.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印与现文件的差，不覆盖。有把握的差异再写入 MANUAL_GOLD_PAGES 后 --write",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="覆盖写入黄金集。默认不写，避免一次静默改尺子",
    )
    parser.add_argument(
        "--categories",
        default="",
        help="只对照这些题型，逗号分隔，如 product_enum,compliance_risk,numeric_financial",
    )
    args = parser.parse_args()
    wanted = {item.strip() for item in args.categories.split(",") if item.strip()}

    items = build_items()
    missing = [item for item in items if not item["gold_pages"]]
    if missing:
        print(f"WARNING: {len(missing)} items without gold_pages:", file=sys.stderr)
        for item in missing:
            print(f"  {item['id']} {item['question']}", file=sys.stderr)

    if args.dry_run or not args.write:
        if not OUT_PATH.is_file():
            print(f"no existing golden at {OUT_PATH}; pass --write to create")
            if missing:
                sys.exit(1)
            return
        current = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        current_by_id = {row["id"]: row for row in current.get("items") or []}
        diffs = 0
        for item in items:
            if wanted and item["category"] not in wanted:
                continue
            old = current_by_id.get(item["id"])
            old_pages = (old or {}).get("gold_pages")
            new_pages = item["gold_pages"]
            if old_pages != new_pages:
                diffs += 1
                print(
                    f"{item['id']} {item['category']} {item['question']}\n"
                    f"  old={old_pages}\n  new={new_pages}"
                )
        print(f"diff_count={diffs} compared={sum(1 for it in items if not wanted or it['category'] in wanted)}")
        if not args.write:
            print("not written (pass --write after reviewing MANUAL_GOLD_PAGES)")
            if missing:
                sys.exit(1)
            return

    categories: dict[str, int] = {}
    for item in items:
        categories[item["category"]] = categories.get(item["category"], 0) + 1

    payload = {
        "version": "rag-retrieval-v1",
        "description": (
            "RAG 检索评测黄金集 100 条：覆盖 5 家 2024 年报（比亚迪/长城/美的/格力/三一），"
            "含财务数字、比率、产品列举、分部业务、合规风险、治理、ESG、战略与同比等题型。"
            "gold_pages 由 doc_chunks 关键词探测 + 人工 override 生成，评测指标为 Recall@k / MRR / nDCG@k / citation_accuracy（page 粒度，gold 页同等相关）。"
        ),
        "default_params": {
            "top_k": 12,
            "min_score": 0.42,
            "metrics": ["recall_at_k", "mrr", "ndcg_at_k", "citation_accuracy", "page_hit_at_k"],
        },
        "category_counts": categories,
        "items": items,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} items to {OUT_PATH}")
    print("Categories:", categories)
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
