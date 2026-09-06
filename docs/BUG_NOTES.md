# Bug 笔记 · RegOps Copilot

> 专门收集开发过程中遇到的问题：**现象 → 根因 → 修复 → 状态**。  
> 新 bug 请按文末 [模板](#新增条目模板) 追加，已修复条目保留作复盘参考。

**最后更新：** 2026-08-21

---

## 快速索引

| ID | 模块 | 标题 | 状态 |
|----|------|------|------|
| [BUG-001](#bug-001-新对话无法切换--标题异常) | 前端 · 会话 | 新对话无法切换 / 标题异常 | ✅ 已修复 |
| [BUG-002](#bug-002-点击会话后列表顺序跳动) | 前端 · 会话 | 点击会话后列表顺序跳动 | ✅ 已修复 |
| [BUG-003](#bug-003-rag-检索被年报页眉挤占) | RAG · 检索 | RAG 检索被年报页眉挤占 | ✅ 已修复 |
| [BUG-004](#bug-004-表格数据未进入-chunk) | Ingest · 分块 | 表格数据未进入 chunk | ✅ 已修复 |
| [BUG-005](#bug-005-token-显示偏大误用-total) | 前端 · 统计 | Token 显示偏大（误用 total） | ✅ 已修复 |
| [BUG-006](#bug-006-顶部导航整栏-hover-触发菜单) | 前端 · 导航 | 顶部导航整栏 hover 触发菜单 | ✅ 已修复 |
| [BUG-007](#bug-007-cleaner-未实现噪声清洗) | Ingest · 清洗 | cleaner 未实现噪声清洗 | ✅ 已修复 |
| [BUG-008](#bug-008-rag-无公司年份范围过滤) | RAG · 检索 | RAG 无公司/年份范围过滤 | ✅ 已修复 |
| [BUG-009](#bug-009-车型列举问题未命中第22页) | RAG · 检索 | 车型列举问题未命中第 22 页 | 🟡 回归（Hybrid 架构） |
| [BUG-010](#bug-010-评测黄金集-gold_pages-自动探测误标) | Eval · 黄金集 | 评测黄金集 gold_pages 自动探测误标 | 🟡 部分修复 |
| [BUG-011](#bug-011-节标题 buried-在-chunk-末尾) | Ingest · 分块 | 节标题 buried 在 chunk 末尾 | 🔴 待修 |
| [BUG-012](#bug-012-同页去重导致列举题缺段) | RAG · 检索 | 同页去重导致列举题缺段 | ⏸ 已知限制 |
| [BUG-013](#bug-013-rag-013-第一节风险-top5-未命中) | Eval · RAG | rag-013 第一节风险 top-5 未命中 | 🟡 部分修复 |

---

## 已记录条目

### BUG-001 · 新对话无法切换 / 标题异常

- **发现时间：** 2026-08-20
- **模块：** 前端 · `web/src/utils/chatSessions.ts` · `ChatPanel.vue`
- **现象：** 新建对话标题固定为「新对话」，侧边栏点击无法切换会话；消息与 session_id 不同步。
- **根因：** 会话列表与 `localStorage` 读写逻辑不完整；切换时未正确 `storeSessionId` / `loadChatMessages`。
- **修复：** 完善 `upsertChatSession`、`listChatSessions`、bridge 注入；新对话默认标题 `新对话 · HH:mm`，首条用户消息后自动派生标题。
- **状态：** ✅ 已修复
- **相关文件：** `chatSessions.ts`, `chatStorage.ts`, `ChatPanel.vue`, `PageSidebar.vue`

---

### BUG-002 · 点击会话后列表顺序跳动

- **发现时间：** 2026-08-20
- **模块：** 前端 · 会话列表
- **现象：** 仅切换查看历史对话，侧边栏顺序也会变，最新对话被顶到最上。
- **根因：** 每次 `touchSessionMeta` 都 `moveToFront: true` 或等价逻辑。
- **修复：** `upsertChatSession` 支持 `{ moveToFront: false }`；切换会话时不更新 `updatedAt` 顺序，仅在新消息/新建时置顶。
- **状态：** ✅ 已修复

---

### BUG-003 · RAG 检索被年报页眉挤占

- **发现时间：** 2026-08-20
- **模块：** RAG · `python-ai/app/rag/service.py`
- **现象：** 问「比亚迪2024年研发投入是多少」，AI 答「文档中未找到相关信息」；引用只有「比亚迪股份有限公司2024年年度报告全文」+ 页码。PDF 第 14 页明明有「研发投入约为542亿元」。
- **根因：**
  1. 年报每页重复页眉「…2024年年度报告全文」被切成 **37+ 个近 duplicate chunk**，向量相似度 **~0.765**，占满 top-5。
  2. 含答案的正文 chunk（第 3 / 14 页）相似度 **~0.53–0.66**，排在 30 名开外，**从未进入 LLM 上下文**。
  3. LLM 按 system prompt 要求，在片段无依据时正确返回「未找到」——**不是模型胡编，是检索喂错了片段**。
- **修复：**
  1. `app/rag/retrieval.py`：过滤页眉噪声 chunk；扩大 fetch 再过滤；查询扩展 + 关键词 ILIKE 补检。
  2. `app/ingest/cleaner.py`：入库前剥离页眉行。
  3. re-ingest `002594_2024` 后页眉 chunk **0 条**，检索 top-1 为第 3 页「542 亿元」。
- **验证：**
  ```bash
  cd python-ai && .venv/bin/python - <<'PY'
  from app.rag.service import retrieve_hits_for_docs
  hits = retrieve_hits_for_docs(question="比亚迪2024年研发投入是多少", doc_ids=["002594_2024"], top_k=5)
  for h in hits: print(h.metadata.get("page"), h.content[:80])
  PY
  ```
- **状态：** ✅ 已修复
- **教训：** RAG 失败先查 **DB 里 chunk 内容** 和 **top-k 实际命中**，不要先怀疑 LLM。

---

### BUG-004 · 表格数据未进入 chunk

- **发现时间：** 2026-08-20
- **模块：** Ingest · `python-ai/app/ingest/chunker.py`
- **现象：** 正式财务报表「研发费用」531.9 亿元（`53,194,745` 千元）搜不到；chunk 里只有「4、研发投入」小节标题。
- **根因：** `chunk_page_blocks` 只索引 `PageBlock.text`，**忽略 `block.tables[].markdown`**。
- **修复：** `_page_indexable_text()` 合并正文 + 表格 markdown；metadata 增加 `has_table`。re-ingest 后 BYD chunk **420 → 886**，含研发支出表的 chunk **4 条**。
- **状态：** ✅ 已修复
- **备注：** 叙事口径「542 亿元」（董事长致辞）与报表口径「531.9 亿元」（研发支出表）并存，回答时应说明来源差异。

---

### BUG-005 · Token 显示偏大（误用 total）

- **发现时间：** 2026-08-20
- **模块：** 前端 · `ChatPanel.vue` · `utils/tokens.ts`
- **现象：** 短回复下方显示「Token 1,101」，而同屏另一条仅「Token 85」。
- **根因：** `completion_tokens` 缺失时 fallback 逻辑用 `total_tokens && prompt_tokens` 判断；`prompt_tokens === 0` 为 falsy，误用 **total（输入+输出）** 展示。
- **修复：** `resolveCompletionTokens()` 用 `!= null` 判断；UI 区分「输入 Token / 输出 Token / 上下文 Token」。
- **状态：** ✅ 已修复

---

### BUG-006 · 顶部导航整栏 hover 触发菜单

- **发现时间：** 2026-08-20
- **模块：** 前端 · `AppShell.vue`
- **现象：** 鼠标移到 Logo、用户头像等顶部任意区域都会展开功能导航。
- **根因：** `@mouseenter` / `@mouseleave` 绑在整个 `<header>` 上。
- **修复：** 仅「功能导航」按钮 + 下拉面板绑定 hover；按钮到面板之间 120ms 延迟防闪关。
- **状态：** ✅ 已修复

---

### BUG-007 · cleaner 未实现噪声清洗

- **发现时间：** 2026-08-20（排查 BUG-003 时发现）
- **模块：** Ingest · `python-ai/app/ingest/cleaner.py`
- **现象：** `NOISE_PATTERNS.md` 已定义页眉/Disclaimer 规则，但 cleaner 长期 **透传占位**。
- **根因：** W2-1 清单未完成，`clean_page_blocks` 直接 return 原 blocks。
- **修复：** 实现 `_ANNUAL_HEADER_LINE_RE`、免责声明行过滤；统计 `annual_header_lines` 命中数。
- **状态：** ✅ 已修复
- **后续：** 双栏硬换行、跨页表头 dedupe 仍待补充（见 `NOISE_PATTERNS.md` §1.3–1.5）。

---

### BUG-008 · RAG 无公司/年份范围过滤

- **发现时间：** 2026-08-20
- **模块：** RAG · `python-ai/app/rag/company_scope.py`
- **现象：** 5 家公司年报 ~2000+ chunk 全局竞争 top-5，跨公司噪声风险高。
- **根因：** `collect_rag_doc_ids` 叠加全部 ready 文档，检索无 `company_code` / `report_year` 过滤。
- **修复：** `filter_doc_ids_for_question()`：问题含「比亚迪」「002594」「2024」等时收窄到 `002594_2024`。
- **状态：** ✅ 已修复
- **后续：** 别名表 `_COMPANY_ALIASES` 需随语料库扩展；可考虑从 `pdf_document.title` 自动构建。

---

### BUG-009 · 车型列举问题未命中第 22 页

- **发现时间：** 2026-08-20（2026-08-21 复盘回归）
- **模块：** RAG · `python-ai/app/rag/service.py` · `retrieval.py` · `reranker.py` · `config.py`
- **现象：** 问「2024年长城新推出的车型有哪些」（评测 **rag-027**），gold 页 **21–23**（节标题 + 车型列举 + 灵魂跨页）。检索 top-12 页码为 `20, 126, 19, 21, 13, 22, 23, …`；**top-5 仅命中 p21**，p22（核心答案页）排 **#6**，MRR=0.25。
- **根因（2026-08-21 pipeline trace）：**
  1. **分块：** p21 c36 末尾才是「本集团 2024 年新推出的车型」，前面大段出海/芯片/氢能；向量 #2、关键词 #1，RRF 综合 **#1**，但内容主体并非车型列举（见 [BUG-011](#bug-011-节标题-buried-在-chunk-末尾)）。
  2. **关键词路未召回 p22：** `extract_keyword_terms` 抽出 `新推出/推出/车型有哪些` 等，**不含「上市」「哈弗」「坦克」**；p22 正文用「上市」而非「推出」，**p22/p23 未进关键词 top-30**。
  3. **向量路 p22 偏低：** 车型列表 chunk（p22 c37）在向量 top-80 仅 **#45**；RRF 融合后排 **#28**。
  4. **精排：** Cross-Encoder（`bge-reranker-v2-m3`）将 p22 从 #28 拉到 **#6**，但仍落后于 p20（灵魂 S2000）、p126（ESG）、p19、p21。
  5. **同页去重：** `rag_max_chunks_per_page=1`，p22 的 c37/c38 只能留一条（见 [BUG-012](#bug-012-同页去重导致列举题缺段)）。
- **历史修复说明（2026-08-20 条目，当前代码已不存在）：** 曾记录 `merge_hits`、`_rerank_hits`、`_ensure_product_category_coverage` 等；现网已改为 **向量 + 关键词 → RRF → Cross-Encoder 精排 → 同页去重**，上述函数 **不在当前仓库**，该次修复视为 **未保留 / 回归**。
- **RRF / 精排 / 去重各做什么（rag-027 实例）：**

  | 阶段 | 作用 | p21 | p22 | p23 |
  |------|------|-----|-----|-----|
  | 向量召回 | embedding 相似度 top-80 | #2 | #45 | #15 |
  | 关键词召回 | ILIKE OR 匹配 top-30 | #1 | 未进榜 | 未进榜 |
  | **RRF** | `2×1/(60+向量名次)+1×1/(60+关键词名次)` 合并 | **#1** | **#28** | #20 |
  | **精排** | 问题+chunk 逐对打分重排（80 候选） | #4 | **#6** | #7 |
  | **去重** | 同页最多 1 chunk，取 top-12 | 留 c36 | 留 c37 或 c38 | 常留 c42 |

- **验证：**
  ```bash
  cd python-ai && .venv/bin/python - <<'PY'
  from app.rag.service import retrieve_hits_with_trace
  hits, pipe = retrieve_hits_with_trace(
      question="2024年长城新推出的车型有哪些",
      doc_ids=["601633_2024"], top_k=12)
  for i, h in enumerate(hits, 1):
      print(i, h.metadata.get("page"), (h.content or "")[:60])
  print("keyword_terms:", pipe.get("keyword_terms"))
  PY
  ```
- **状态：** 🟡 回归（Hybrid 架构下仍待优化）
- **建议修复（优先级）：**
  1. 节标题处切 chunk（[BUG-011](#bug-011-节标题-buried-在-chunk-末尾)）
  2. 列举类问题关键词补充 `上市、新款、发布` 或车型 probe 词
  3. 列举题 `rag_max_chunks_per_page=2` 或动态放宽（[BUG-012](#bug-012-同页去重导致列举题缺段)）
- **相关文件：** `service.py`, `retrieval.py`, `reranker.py`, `config.py`, `eval/golden/rag_retrieval_100.json`（rag-027）
- **备注：** 评测 gold `[21, 22, 23]` **正确**（跨页连续板块）；Recall@12 可命中，但 top-5 / 答全仍不足。

---

### BUG-010 · 评测黄金集 gold_pages 自动探测误标

- **发现时间：** 2026-08-21
- **模块：** Eval · `eval/scripts/build_rag_retrieval_golden.py` · `eval/golden/rag_retrieval_100.json`
- **现象：**
  - **rag-008**（比亚迪新车型）：自动探测曾标 `[29, 3, 13, 15, 16]`；p29 为研发技术表，p3/13/15 为致辞/行业/战略，**真正列举在 p16–20**。
  - **rag-027**（长城新车型）：人工 override `[21, 22, 23]` 正确；自动探测若只靠 `推出/上市/发布` 会误吸无关页。
  - 易与 **印刷页码 / PDF 物理页码** 混淆（脚注「21/393」≠ 误以为 p23 无关）。
- **根因：** `probe_pages()` 按关键词 ILIKE + 简单打分，**不识别节标题、不处理跨页板块**；`MANUAL_GOLD_PAGES` 覆盖不足时误标。
- **修复：**
  1. rag-008 改为 `MANUAL_GOLD_PAGES` → `[16, 17, 18, 19, 20]`；probe 词改为 `全新车型/正式上市/元UP/秦L`。
  2. rag-027 保持 `[21, 22, 23]`。
  3. `docs/eval_rag_retrieval.md` 补充：gold 用 **PDF 物理页码**，跨页段落需整段标注。
- **验证：** 重新跑 `build_rag_retrieval_golden.py`，对照 PDF 抽检 product_enum 类 10 题。
- **状态：** 🟡 部分修复（已知题已 override，其余 category 仍建议抽检）
- **相关文件：** `eval/scripts/build_rag_retrieval_golden.py`, `eval/golden/rag_retrieval_100.json`, `docs/eval_rag_retrieval.md`

---

### BUG-011 · 节标题 buried 在 chunk 末尾

- **发现时间：** 2026-08-21（排查 BUG-009 / rag-027）
- **模块：** Ingest · 分块策略（`chunker.py` / 会话 pipeline）
- **现象：** 长城年报 p21 **最后一行**为「本集团 2024 年新推出的车型 21/393」，但该 chunk（c36）主体是出海/GWM 战略（500+ 字）。检索时向量/关键词命中 chunk **前半**，RRF 把 p21 顶到 #1，LLM 上下文却几乎看不到节标题。
- **根因：** 分块按固定长度/块边界切，**不在 MD 节标题 / 「新推出的车型」类小节边界切分**。
- **修复：** 待做——入库或 chunk 阶段识别小节标题（正则或 parse 结构），**标题单独成 chunk 或与紧随正文合并**，避免标题落在长 chunk 末尾。
- **状态：** 🔴 待修
- **相关文件：** `python-ai/app/ingest/chunker.py`
- **备注：** 比亚迪 p16「推出多款全新车型」+ 车型名列表同理，p16–20 为连续板块。

---

### BUG-012 · 同页去重导致列举题缺段

- **发现时间：** 2026-08-21（排查 BUG-009）
- **模块：** RAG · `python-ai/app/rag/retrieval.py` · `config.py`
- **现象：** p22 有 c37（车型名列表）与 c38（H6/H9 上市详情）两条均高度相关；精排后 `apply_page_diversity(max_per_page=1)` **只留一条**，答「有哪些新车型」时可能缺 H6/H9 细节。p23 的 c39（灵魂跨页顶）与 c42（灵魂详情）同理。
- **根因：** 设计取舍——`rag_max_chunks_per_page=1` 为避免 top-k 被少数页占满、减重复、控 token；**未区分「列举题需同页多条」**。
- **修复（可选）：**
  1. 配置 `rag_max_chunks_per_page: 2`；
  2. 或检测「有哪些/列举/新车型」时动态放宽；
  3. 或依赖 [BUG-011](#bug-011-节标题-buried-在-chunk-末尾) 让一页一条即够。
- **状态：** ⏸ 已知限制（产品/评测目标不同：Recall@k 看页码，答全看 chunk）
- **相关文件：** `retrieval.py`（`apply_page_diversity`）, `config.py`

---

### BUG-013 · rag-013 第一节风险 top-5 未命中

- **发现时间：** 2026-08-21
- **模块：** Eval · RAG · `rag_retrieval_runner.py` · `retrieval.py`
- **评测条目：** **rag-013** —「比亚迪年报第一节披露了哪些主要风险」
- **现象：** 明细里 gold **p5**，检索前几名 `97, 138, 140, 72, 100`（审计/内控/ESG 等含「风险」字样），**top-5 无 p5**；报告仍标 **page_hit_at_k=是**（因 p5 在 **top-12 第 10 位**，MRR=0.1）。
- **gold p5 内容（第一节 重要提示）：**
  - 并非列举经营风险清单，而是声明：**「不存在…严重不利影响的有关风险因素」**；
  - 并写明：**「可能面临的风险因素，详见本报告第三节管理层讨论与分析…」**。
  - 故本题 gold **p5 对「第一节说了什么」是对的**；若用户期望的是**风险清单正文**，应在 **p13+（第三节）**，题目与 gold 需区分（见下）。
- **根因：**
  1. **指标 vs 观感：** Recall@k（k=12）命中即「是」，前端/明细若只展示 top-5，会像「没命中」。
  2. **关键词未抽「第一节」：** `extract_keyword_terms` 原先无 `第X节`，问句里的节次信息未参与 ILIKE；「风险」泛匹配到审计报告「信用风险」、内控「缺陷」、ESG 等（p97/138/140/72）。
  3. **向量：** p5 在向量 top-80 约 **#75**，精排后才进 top-12。
- **修复：**
  1. `extract_keyword_terms` 增加 `第[一二…]+节` 抽取（已合入 `retrieval.py`）。
  2. 黄金集 probe 词改为 `第一节/风险因素/可能面临`；`MANUAL_GOLD_PAGES` 保持 `[5]` 并加注释。
  3. **待产品确认：** 是否另增一题「第三节经营面临的主要风险」gold **p13+**，与本题（第一节表述）拆开。
- **验证：**
  ```bash
  cd python-ai && .venv/bin/python - <<'PY'
  from app.rag.service import retrieve_hits_for_docs
  hits = retrieve_hits_for_docs(
      question="比亚迪年报第一节披露了哪些主要风险",
      doc_ids=["002594_2024"], top_k=12)
  pages = [h.metadata.get("page") for h in hits]
  print(pages[:5], "p5@", pages.index(5)+1 if 5 in pages else None)
  PY
  ```
- **状态：** 🟡 部分修复（关键词已补「第一节」；精排/top-5 仍待观察）
- **相关文件：** `retrieval.py`, `eval/golden/rag_retrieval_100.json`, `eval/scripts/build_rag_retrieval_golden.py`

---

## 前端 / UX 小问题（已处理，未单独编号）

| 问题 | 处理 |
|------|------|
| 输入框过大、模型/PDF 按钮位置 | 单行布局：📎 左 · 输入中 · 模型右 |
| 每条 AI 回复重复免责声明 | 移至输入框下方 footer 统一展示 |
| 连接状态「已连接/刷新」占 footer | 改为模型选择器绿/红点；断开时在输入框上弹提示 |
| 消息区滚动条过长太显眼 | 细滚动条 + hover 显示 + 轨道上下留白 |
| AI 回复底部重复「模型：deepseek」 | 已移除（模型仅在输入栏选择器显示） |

---

## 排查备忘

### RAG 答「文档中未找到」

1. 文档是否 `ingest_status=ready`？`SELECT doc_id, page_count FROM pdf_document WHERE doc_id LIKE '%代码%';`
2. 答案是否在 chunk 里？`SELECT chunk_index, metadata->>'page', left(content,120) FROM doc_chunks WHERE content LIKE '%关键词%';`
3. 检索 top-k 命中什么？见 BUG-003 / BUG-009 验证脚本。
4. **Hybrid pipeline 分阶段查什么？**（2026-08-21）
   - `pipeline["keyword_terms"]`：关键词是否漏「上市/车型名」？
   - `pipeline["vector_top"]` / `keyword_top`：gold 页在哪一路、第几名？
   - RRF 后候选序 → 精排是否拉升 gold 页？同页去重丢了哪条 chunk？
   - 评测明细：`eval/reports/.../report.json` 中 `retrieved_pages` vs `gold_pages`（Recall@k 看页码，不等于 context 答全）。
5. 是否被页眉 chunk 挤占？`SELECT COUNT(*) FROM doc_chunks WHERE content LIKE '%年度报告全文%';`
6. 改 ingest 后是否 **re-ingest**？`python scripts/ingest_pdf_to_vectors.py ../data/raw/xxx.pdf`

### 评测黄金集 gold_pages 抽检

1. product_enum / 列举题优先 **人工对照 PDF**（自动 `probe_pages` 易误标，见 BUG-010）。
2. 长城 rag-027 正确 gold：**[21, 22, 23]**（p21 节标题 + p22 车型 + p23 灵魂跨页）。
3. 比亚迪 rag-008 正确 gold：**[16, 17, 18, 19, 20]**（非 p29 研发表）。
4. 页码 = **PDF 物理页**（从文件第 1 页计），与脚注印刷页码可能差若干页。
5. 重生成：`cd python-ai && .venv/bin/python ../eval/scripts/build_rag_retrieval_golden.py`

### 服务起不来

| 服务 | 端口 | 命令 |
|------|------|------|
| PostgreSQL | 5432 | `docker compose up -d db` |
| Python AI | 8000 | `cd python-ai && .venv/bin/uvicorn app.main:app --reload` |
| Java BFF | 8080 | `cd java-service && mvn spring-boot:run` |
| Web | 5173 | `cd web && npm run dev` |

---

## 新增条目模板

复制以下块填写并追加到「已记录条目」区，同时在「快速索引」加一行。

```markdown
### BUG-XXX · （简短标题）

- **发现时间：** YYYY-MM-DD
- **模块：** 前端 / RAG / Ingest / Java BFF / …
- **现象：** 用户看到什么？复现步骤？
- **根因：** 技术原因（附文件路径更好）
- **修复：** 做了什么 / PR / commit
- **验证：** 怎么确认已好？
- **状态：** 🔴 待修 / 🟡 进行中 / ✅ 已修复 / ⏸ 搁置
- **相关文件：** `path/to/file`
- **备注：** 教训、后续优化
```

---

## 待观察 / 已知限制

- [ ] 其他 4 家公司年报尚未用新 chunker（含表格）re-ingest，财务表格式问题可能复现
- [ ] `NOISE_PATTERNS.md` 中双栏换行、跨页表头 dedupe 仍未实现
- [ ] 会话 PDF 与会司语料库检索仍为同一套 top-k，未对会话文档加权
- [ ] 旧 localStorage 缓存消息可能仍带错误 `totalTokens` 数字，重新提问即正常
- [ ] **BUG-009** 车型列举在 Hybrid（RRF + Cross-Encoder）下回归；top-12 可命中 p22，top-5 仍不足
- [ ] **BUG-012** `rag_max_chunks_per_page=1`：列举题同页多条 relevant chunk 时故意只留 1 条
- [ ] 评测 **Recall@k**（页码命中）与线上 **答全**（chunk 内容完整）目标不一致
- [ ] 黄金集 100 题中 product_enum 等仍建议按 PDF 抽检（BUG-010）

---

*维护者：开发过程中遇到 bug 随时追加。修复后不要删除条目，改状态为 ✅ 并保留根因供复盘。*
