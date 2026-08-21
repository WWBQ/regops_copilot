<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { createLabelTask, downloadLabelTemplate } from '../../api/labeling'
import type { UrlType } from '../../types/labeling'

const router = useRouter()
const name = ref('')
const desc = ref('')
const urlType = ref<UrlType>('pdf')
const file = ref<File | null>(null)
const options = ref(['OK', '有问题', '跳过'])
const optionDraft = ref('')
const error = ref('')
const submitting = ref(false)

function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
}

function addOption() {
  const text = optionDraft.value.trim()
  if (!text) {
    return
  }
  if (options.value.includes(text)) {
    error.value = '该选项已存在'
    return
  }
  if (text.length > 40) {
    error.value = '单个选项不超过 40 字'
    return
  }
  if (options.value.length >= 20) {
    error.value = '最多 20 个选项'
    return
  }
  options.value.push(text)
  optionDraft.value = ''
  error.value = ''
}

function removeOption(index: number) {
  options.value.splice(index, 1)
}

const downloading = ref(false)

async function onDownloadTemplate() {
  error.value = ''
  downloading.value = true
  try {
    await downloadLabelTemplate()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '下载模板失败'
  } finally {
    downloading.value = false
  }
}

async function submit() {
  error.value = ''
  if (!name.value.trim()) {
    error.value = '请填写任务名称'
    return
  }
  if (!file.value) {
    error.value = '请上传按模板填写的 .xlsx'
    return
  }
  if (!file.value.name.toLowerCase().endsWith('.xlsx')) {
    error.value = '只接受 .xlsx，请先下载标准模板'
    return
  }
  if (!options.value.length) {
    error.value = '至少添加一个标注选项'
    return
  }
  submitting.value = true
  try {
    const form = new FormData()
    form.set('name', name.value.trim())
    form.set('desc', desc.value.trim())
    form.set('url_type', urlType.value)
    form.set('label_options', JSON.stringify(options.value))
    form.set('file', file.value)
    const task = await createLabelTask(form)
    await router.push(`/quality/review/${task.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="page">
    <header class="chat-header">
      <div>
        <h1>创建标注任务</h1>
        <p>请先下载标准模板，按列填写后再上传。只接受 <code>.xlsx</code>。</p>
      </div>
      <div class="header-actions">
        <button type="button" class="ghost-btn" :disabled="downloading" @click="onDownloadTemplate">
          {{ downloading ? '下载中…' : '下载标准模板' }}
        </button>
        <button type="button" class="ghost-btn" @click="router.push('/quality/review')">返回大厅</button>
      </div>
    </header>

    <section class="spec-card">
      <h2>数据格式（必须遵守）</h2>
      <p>文件：Excel 工作簿 <code>.xlsx</code>，仅第一张表。列名必须完全一致，不要增删列。</p>
      <table class="spec">
        <thead>
          <tr>
            <th>列名</th>
            <th>必填</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><code>id</code></td>
            <td>是</td>
            <td>条目唯一 ID，不能重复、不能为空</td>
          </tr>
          <tr>
            <td><code>url</code></td>
            <td>是</td>
            <td>必须以 http:// 或 https:// 开头</td>
          </tr>
          <tr>
            <td><code>text</code></td>
            <td>是（列必须有，内容可空）</td>
            <td>待核对原文</td>
          </tr>
          <tr>
            <td><code>info</code></td>
            <td>否</td>
            <td>补充信息，可空</td>
          </tr>
        </tbody>
      </table>
    </section>

    <form class="form-card" @submit.prevent="submit">
      <label>
        任务名称
        <input v-model="name" required />
      </label>
      <label>
        任务描述
        <input v-model="desc" />
      </label>
      <label>
        预览类型
        <select v-model="urlType">
          <option value="pdf">pdf</option>
          <option value="html">html</option>
          <option value="text">text</option>
        </select>
      </label>
      <div class="options-block">
        <span class="options-label">标注选项</span>
        <div class="chips">
          <span v-for="(opt, index) in options" :key="opt" class="chip">
            {{ opt }}
            <button type="button" class="chip-remove" @click="removeOption(index)">删除</button>
          </span>
        </div>
        <div class="option-add">
          <input
            v-model="optionDraft"
            placeholder="输入选项后回车或点添加，例如：通过、需复核"
            @keydown.enter.prevent="addOption"
          />
          <button type="button" class="ghost-btn" @click="addOption">添加</button>
        </div>
      </div>
      <label>
        按模板填写的 .xlsx
        <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" @change="onFile" />
      </label>
      <p v-if="error" class="error">{{ error }}</p>
      <button type="submit" class="send-btn" :disabled="submitting">
        {{ submitting ? '创建中…' : '创建' }}
      </button>
    </form>
  </section>
</template>

<style scoped>
.page {
  max-width: 720px;
  margin: 0 auto;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.spec-card {
  margin-top: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 20px;
  box-shadow: var(--shadow);
}

.spec-card h2 {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--text-strong);
}

.spec-card p {
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 13px;
}

.spec {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.spec th,
.spec td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}

.spec th {
  color: var(--muted);
  font-weight: 600;
}

.form-card {
  margin-top: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow);
  display: grid;
  gap: 14px;
}

label,
.options-block {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}

input,
select {
  font: inherit;
  color: var(--text-strong);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  background: #fbfdff;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #ecfeff;
  color: #0f766e;
  font-weight: 600;
}

.chip-remove {
  border: none;
  background: transparent;
  color: #0f766e;
  cursor: pointer;
  padding: 0;
  font-size: 12px;
}

.option-add {
  display: flex;
  gap: 8px;
}

.option-add input {
  flex: 1;
}

.error {
  margin: 0;
  color: var(--danger);
}
</style>
