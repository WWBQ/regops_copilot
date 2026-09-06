<script setup lang="ts">
const roadmap = [
  {
    title: '多步任务编排',
    detail: 'LangGraph 状态图：拆解「查年报 → 核对数字 → 生成结论」等合规分析链。',
    phase: 'W6',
  },
  {
    title: '工具调用',
    detail: 'RAG 检索、受控问数（fin_metric）、制度库查询；每步可审计、可重试。',
    phase: 'W5–W6',
  },
  {
    title: '任务级状态（非闲聊记忆）',
    detail: 'Checkpoint 保存当前任务进度与中间结果，不将整段对话历史塞进检索。',
    phase: 'W6',
  },
  {
    title: '数字校验 + 人工复核',
    detail: 'Agent 节点校验财报数字与引用；高风险结论进入 HITL 待审。',
    phase: 'W6–W9',
  },
]

const compareRows = [
  { dim: '交互模式', rag: '单轮问答', agent: '多步任务 / 工作流' },
  { dim: '检索记忆', rag: '无：每问独立检索', agent: '任务状态，非对话记忆' },
  { dim: '证据链', rag: '单次 trace + 引用', agent: '逐步 trace + 工具日志' },
  { dim: '适用场景', rag: '「年报里风险因素有哪些」', agent: '「对比三家营收并核对管理层口径」' },
]
</script>

<template>
  <section class="page">
    <header class="head">
      <div>
        <p class="phase">W6 · Agent 编排</p>
        <h1>合规 Agent</h1>
        <p class="lead">
          面向<strong>多步合规分析</strong>的任务型助手（开发中）。首页「合规问答」已做
          <strong>单轮分流</strong>（问数查 <code>fin_metric</code>，叙述走 RAG）；本页留给多步编排。
          Agent 仅保留<strong>任务进度</strong>，不把历史闲聊注入检索。
        </p>
      </div>
      <div class="head-actions">
        <router-link to="/" class="ghost-btn">去合规问答（RAG）</router-link>
      </div>
    </header>

    <div class="notice">
      <strong>当前状态：</strong>页面占位 · 后端 <code>python-ai/app/agents/</code> 尚未接入。
      请先用首页：营收/净利润走问数，风险/战略走 RAG。复杂多步分析将在 W6 启用本页。
    </div>

    <div class="grid">
      <article class="card">
        <h2>RAG vs Agent</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>维度</th>
                <th>合规问答（RAG）</th>
                <th>合规 Agent（规划）</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in compareRows" :key="row.dim">
                <td>{{ row.dim }}</td>
                <td>{{ row.rag }}</td>
                <td>{{ row.agent }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="card">
        <h2>路线图</h2>
        <ul class="roadmap">
          <li v-for="item in roadmap" :key="item.title">
            <span class="roadmap-phase">{{ item.phase }}</span>
            <strong>{{ item.title }}</strong>
            <p>{{ item.detail }}</p>
          </li>
        </ul>
      </article>
    </div>

    <article class="card chat-preview">
      <h2>交互预览（未启用）</h2>
      <div class="preview-box">
        <p class="preview-hint">Agent 对话区 · W6 接入 LangGraph 后开放</p>
        <div class="preview-input" aria-disabled="true">
          <span>例如：对比比亚迪、长城、格力 2024 年研发投入占比，并列出引用页码</span>
          <button type="button" disabled>发送</button>
        </div>
      </div>
    </article>
  </section>
</template>

<style scoped>
.page {
  max-width: 960px;
  margin: 0 auto;
}

.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.phase {
  display: inline-block;
  margin: 0 0 8px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 12px;
  font-weight: 600;
}

.head h1 {
  margin: 0 0 8px;
  font-size: 26px;
  color: var(--text-strong);
}

.lead {
  margin: 0;
  max-width: 640px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-muted);
}

.head-actions {
  flex-shrink: 0;
}

.ghost-btn {
  display: inline-block;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
}

.ghost-btn:hover {
  background: #f8fafc;
}

.notice {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid #fde68a;
  background: #fffbeb;
  font-size: 13px;
  line-height: 1.55;
  color: #92400e;
}

.grid {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 16px;
  margin-bottom: 16px;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 20px;
  box-shadow: var(--shadow);
}

.card h2 {
  margin: 0 0 12px;
  font-size: 16px;
  color: var(--text-strong);
}

.table-wrap {
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

th {
  background: #f8fafc;
  color: var(--text-muted);
  font-weight: 600;
}

.roadmap {
  margin: 0;
  padding: 0;
  list-style: none;
}

.roadmap li {
  padding: 10px 0;
  border-bottom: 1px dashed var(--border);
}

.roadmap li:last-child {
  border-bottom: none;
}

.roadmap-phase {
  display: inline-block;
  margin-right: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.roadmap strong {
  display: inline;
  font-size: 14px;
}

.roadmap p {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-muted);
}

.chat-preview {
  margin-bottom: 24px;
}

.preview-box {
  border: 1px dashed var(--border);
  border-radius: 10px;
  background: #fafbfc;
  padding: 16px;
}

.preview-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-muted);
}

.preview-input {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  opacity: 0.7;
}

.preview-input span {
  flex: 1;
  font-size: 13px;
  color: #94a3b8;
}

.preview-input button {
  border: none;
  border-radius: 8px;
  padding: 8px 14px;
  background: #cbd5e1;
  color: #fff;
  font-weight: 600;
  cursor: not-allowed;
}

@media (max-width: 820px) {
  .grid {
    grid-template-columns: 1fr;
  }

  .head {
    flex-direction: column;
  }
}
</style>
