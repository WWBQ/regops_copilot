# Bug 笔记 · RegOps Copilot

> 专门收集开发过程中遇到的问题：**现象 → 根因 → 修复 → 状态**。  
> 新 bug 请按文末 [模板](#新增条目模板) 追加，已修复条目保留作复盘参考。

**最后更新：** 2026-08-20

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
| [BUG-009](#bug-009-车型列举问题未命中第22页) | RAG · 检索 | 车型列举问题未命中第 22 页 | ✅ 已修复 |

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

- **发现时间：** 2026-08-20
- **模块：** RAG · `python-ai/app/rag/retrieval.py` · `service.py` · `config.py`
- **现象：** 问「2024年长城新推出的车型」，AI 只答长城灵魂 S2000 摩托车、Hi4-Z 架构，未列出第 22 页的多款 SUV（坦克 700 Hi4-T、坦克 500 Hi4-Z、蓝山高阶智驾版、新一代哈弗 H6、二代哈弗 H9 等）。
- **根因：**
  1. 第 22 页车型列举 chunk 纯向量相似度约 **0.54–0.72**，排在 **26–37 名**，`top_k=5` 时进不了 LLM 上下文。
  2. 向量 top-5 已满时，**关键词 ILIKE 补检结果被丢弃**，无法把含「坦克」「哈弗」的 chunk 合并进来。
  3. 债券/附注等 chunk 向量分更高，进一步挤占名额。
- **修复：**
  1. **始终合并**向量 + 关键词命中（`merge_hits` 扩大候选池后再截断）。
  2. `_rerank_hits()`：车型类问题对多车型列举片段加分，对债券/附注降权。
  3. `expand_rag_query` / `extract_keyword_terms` 对车型问题补充「哈弗、坦克、蓝山、Hi4、**灵魂、S2000GL、摩托车**」等同义词。
  4. `_rerank_hits()` 对 **S2000GL** 片段加分，对含「高新技术企业/所得税」的 OCR 噪声 chunk 降权；`_ensure_product_category_coverage()` 确保 top-8 含摩托车品类。
  5. `rag_top_k` **5 → 8**；车型类问题 merge 候选池扩大至 **20**。
- **验证：**
  ```bash
  cd python-ai && .venv/bin/python - <<'PY'
  from app.rag.service import retrieve_hits_for_docs
  hits = retrieve_hits_for_docs(question="2024年长城新推出的车型", doc_ids=["601633_2024"], top_k=8)
  for h in hits[:3]: print(h.metadata.get("page"), h.content[:80])
  assert any(h.metadata.get("page") == 22 for h in hits)
  PY
  ```
  预期 top-1 为第 **22** 页（SUV 列举），top-8 含第 **23** 页「长城灵魂 **S2000GL**」（chunk 42）及第 20 页 S2000 上市信息。
- **状态：** ✅ 已修复
- **相关文件：** `retrieval.py`, `service.py`, `config.py`, `tests/test_rag_retrieval.py`
- **备注：** 需 **重新提问**（旧对话缓存不会自动更新）；若 Python 未 `--reload`，需重启 `uvicorn`。

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
3. 检索 top-k 命中什么？见 BUG-003 验证脚本。
4. 是否被页眉 chunk 挤占？`SELECT COUNT(*) FROM doc_chunks WHERE content LIKE '%年度报告全文%';`
5. 改 ingest 后是否 **re-ingest**？`python scripts/ingest_pdf_to_vectors.py ../data/raw/xxx.pdf`

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

---

*维护者：开发过程中遇到 bug 随时追加。修复后不要删除条目，改状态为 ✅ 并保留根因供复盘。*
