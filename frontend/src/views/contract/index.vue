<template>
  <section class="page" data-module="contract">
    <header class="page-head">
      <div>
        <h2>维保合同管理</h2>
        <p class="page-desc">
          按服务单位划分合同归属：本单位只能查看和维护自己的合同，共用服务单位信息只读；
          跨单位改动会被拦下并说明原因。
        </p>
      </div>
      <div class="page-actions">
        <label class="unit-pick">
          <span>当前服务单位</span>
          <select :value="session.serviceUnit" @change="switchUnit(($event.target as HTMLSelectElement).value)">
            <option v-for="unit in writableUnits" :key="unit.name" :value="unit.name">{{ unit.name }}</option>
          </select>
        </label>
        <button class="btn primary" type="button" @click="openCreate">登记维保合同</button>
        <button class="btn" type="button" @click="exportRows">导出合同清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="scope-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        :class="['scope-tab', scope === tab.key ? 'active' : '']"
        @click="switchScope(tab.key)"
      >
        {{ tab.label }}
        <span v-if="tab.key === 'missing' && summary.missing" class="tab-badge">{{ summary.missing }}</span>
      </button>
      <span class="scope-hint">{{ scopeHint }}</span>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>合同编号</span>
        <input v-model="keyword" placeholder="按合同编号检索" />
      </label>
      <label class="filter-item">
        <span>履约状态</span>
        <select v-model="status">
          <option value="">全部</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>归属</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td><button class="link" type="button" @click="openDetail(row)">{{ row['合同编号'] ?? '—' }}</button></td>
          <td>{{ row['服务单位'] || '—' }}</td>
          <td>{{ row['维保设备'] ?? '—' }}</td>
          <td>{{ row['合同金额'] ?? '—' }}</td>
          <td>{{ row['到期日期'] ?? '—' }}</td>
          <td>
            <span :class="['status-tag', statusClass(row['履约状态'])]">{{ row['履约状态'] ?? '—' }}</span>
          </td>
          <td>
            <span v-if="row['归属缺失']" class="scope-tag missing">归属缺失</span>
            <span v-else-if="isShared(row['服务单位'])" class="scope-tag shared">共用·只读</span>
            <span v-else-if="row['服务单位'] === session.serviceUnit" class="scope-tag own">本单位</span>
            <span v-else class="scope-tag other">外单位</span>
          </td>
          <td class="row-actions">
            <template v-if="!row['只读']">
              <button
                v-for="action in availableActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <button class="link" type="button" @click="openAdjust(row)">调整金额/到期</button>
              <button class="link" type="button" @click="openTransfer(row)">变更归属</button>
              <button class="link danger" type="button" @click="removeRow(row)">删除</button>
            </template>
            <template v-else>
              <button class="link" type="button" @click="openDetail(row)">查看</button>
              <button v-if="row['归属缺失']" class="link" type="button" @click="openClaim(row)">认领归属</button>
              <span v-else class="readonly-note">只读</span>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ scopeLabel }}合同记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="okMessage" class="ok-text">{{ okMessage }}</span>
    </footer>

    <!-- 登记 / 调整 / 归属变更 共用弹窗 -->
    <div v-if="form.show" class="modal-mask" @click.self="closeForm">
      <div class="modal">
        <h3>{{ form.title }}</h3>
        <p v-if="form.desc" class="modal-desc">{{ form.desc }}</p>
        <template v-if="form.mode === 'create'">
          <label class="form-line"><span>合同编号</span><input v-model="form.code" placeholder="如 CONT-0100" /></label>
          <label class="form-line"><span>维保设备</span><input v-model="form.equipment" placeholder="维保设备范围" /></label>
          <label class="form-line"><span>合同金额</span><input v-model="form.amount" type="number" placeholder="元" /></label>
          <label class="form-line"><span>到期日期</span><input v-model="form.due" type="date" /></label>
          <p class="modal-desc">归属服务单位固定为当前单位「{{ session.serviceUnit }}」，不能替别家单位登记。</p>
        </template>
        <template v-else-if="form.mode === 'adjust'">
          <label class="form-line"><span>合同金额（元）</span><input v-model="form.amount" type="number" /></label>
          <label class="form-line"><span>到期日期</span><input v-model="form.due" type="date" /></label>
          <p class="modal-desc">保存后履约状态按金额与到期日期重新判定。</p>
        </template>
        <template v-else>
          <label class="form-line">
            <span>目标服务单位</span>
            <select v-model="form.target">
              <option value="">请选择归属单位</option>
              <option v-for="unit in writableUnits" :key="unit.name" :value="unit.name">{{ unit.name }}</option>
            </select>
          </label>
          <p class="modal-desc">归属变更后，历史履约记录仍留在原服务单位名下，不随之搬迁。</p>
        </template>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="button" @click="submitForm">确定</button>
        </div>
      </div>
    </div>

    <!-- 详情弹窗：履约状态与列表、概览取自同一份口径 -->
    <div v-if="detail.show" class="modal-mask" @click.self="detail.show = false">
      <div class="modal wide">
        <h3>合同详情 · {{ detail.row?.['合同编号'] }}</h3>
        <div v-if="detail.row" class="detail-grid">
          <span v-for="field in detailFields" :key="field" class="detail-item">
            <em>{{ field }}</em>
            <strong>{{ detail.row[field] ?? '—' }}</strong>
          </span>
          <span class="detail-item">
            <em>归属范围</em>
            <strong>{{ detail.row['归属缺失'] ? '归属缺失' : (isShared(detail.row['服务单位']) ? '共用单位（只读）' : detail.row['服务单位']) }}</strong>
          </span>
        </div>
        <h4>履约历史（按发生时归属留痕）</h4>
        <table class="data-table history-table">
          <thead>
            <tr><th>时间</th><th>归属单位</th><th>动作</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in detail.history" :key="String(item.id)">
              <td>{{ item['时间'] }}</td>
              <td>{{ item['归属单位'] }}</td>
              <td>{{ item['动作'] }}</td>
              <td>{{ item['说明'] }}</td>
            </tr>
            <tr v-if="!detail.history.length">
              <td colspan="4" class="empty-state">暂无履约历史记录</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="detail.show = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>
type HistoryRow = Record<string, string | number | null>
type ServiceUnit = { name: string; shared: boolean }

const ENDPOINT = '/api/contract'
const columns = ['合同编号', '服务单位', '维保设备', '合同金额', '到期日期', '履约状态']
const detailFields = ['合同编号', '服务单位', '维保设备', '合同金额', '服务期限', '签订人员', '到期日期', '履约状态']
const statuses = ['待签订', '履行中', '已到期', '已终止']

const session = useSessionStore()
const units = ref<ServiceUnit[]>([])
const writableUnits = computed(() => units.value.filter((item) => !item.shared))

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const okMessage = ref('')
const keyword = ref('')
const status = ref('')
const scope = ref<'mine' | 'shared' | 'missing'>('mine')

const summary = reactive({ active: 0, expired: 0, unsigned: 0, missing: 0, totalAmount: 0 })
const stats = computed(() => [
  { label: '在履合同', value: summary.active },
  { label: '已到期', value: summary.expired },
  { label: '待签订', value: summary.unsigned },
  { label: '归属缺失', value: summary.missing },
  { label: '合同总金额（元）', value: summary.totalAmount },
])

const tabs = [
  { key: 'mine' as const, label: '本单位合同' },
  { key: 'shared' as const, label: '共用单位（只读）' },
  { key: 'missing' as const, label: '归属缺失待认领' },
]
const scopeLabel = computed(() => tabs.find((item) => item.key === scope.value)?.label ?? '')
const scopeHint = computed(() => {
  if (scope.value === 'shared') return '集团共用服务单位的合同全平台只读，任何单位都不能改动。'
  if (scope.value === 'missing') return '归属缺失的合同单独列出，认领前只读，名录内单位可认领归属。'
  return `当前只展示归属「${session.serviceUnit}」的合同；别家单位合同不可见、不可改。`
})
const emptyText = computed(() => {
  if (scope.value === 'missing') return '暂无归属缺失的合同'
  if (scope.value === 'shared') return '暂无共用服务单位合同'
  return `「${session.serviceUnit}」名下暂无合同，可先登记维保合同`
})

const form = reactive({
  show: false,
  mode: 'create' as 'create' | 'adjust' | 'transfer',
  title: '',
  desc: '',
  id: 0,
  code: '',
  equipment: '',
  amount: '',
  due: '',
  target: '',
})

const detail = reactive<{ show: boolean; row: Row | null; history: HistoryRow[] }>({
  show: false,
  row: null,
  history: [],
})

function isShared(name: unknown): boolean {
  return units.value.some((item) => item.shared && item.name === name)
}

function statusClass(value: unknown): string {
  if (value === '履行中') return 'running'
  if (value === '已到期') return 'expired'
  if (value === '已终止') return 'stopped'
  return 'draft'
}

function availableActions(row: Row): string[] {
  const value = String(row['履约状态'] ?? '')
  if (value === '已终止') return []
  const list = ['终止合同']
  if (value !== '已到期') list.unshift('标记到期')
  if (value === '待签订') list.unshift('确认签订')
  return list
}

function switchUnit(name: string) {
  session.setServiceUnit(name)
  scope.value = 'mine'
  void reload()
}

function switchScope(next: 'mine' | 'shared' | 'missing') {
  scope.value = next
  void reload()
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

function unitQuery(extra?: string): string {
  const params = new URLSearchParams()
  params.set('unit', session.serviceUnit)
  if (extra) return `${params.toString()}&${extra}`
  return params.toString()
}

async function loadUnits() {
  try {
    const response = await request(`${ENDPOINT}/units`)
    if (response.ok) {
      const payload = await response.json()
      units.value = payload.items ?? []
    }
  } catch {
    units.value = []
  }
}

async function reload() {
  errorMessage.value = ''
  okMessage.value = ''
  const params = new URLSearchParams()
  params.set('unit', session.serviceUnit)
  params.set('scope', scope.value)
  if (keyword.value) params.set('keyword', keyword.value.trim())
  if (status.value) params.set('status', status.value)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) throw new Error('维保合同列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    Object.assign(summary, {
      active: payload.summary?.active ?? 0,
      expired: payload.summary?.expired ?? 0,
      unsigned: payload.summary?.unsigned ?? 0,
      missing: payload.summary?.missing ?? 0,
      totalAmount: payload.summary?.totalAmount ?? 0,
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '维保合同列表读取失败'
  }
}

async function postAction(path: string, body: object, successHint: string) {
  try {
    const response = await request(path, { method: 'POST', body: JSON.stringify(body) })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '操作未生效，请稍后重试')
    }
    okMessage.value = payload.message || successHint
    errorMessage.value = ''
    await reload()
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '维保合同操作失败'
    return false
  }
}

async function runAction(action: string, row: Row) {
  await postAction(
    `${ENDPOINT}/${row.id}/actions?${unitQuery()}`,
    { values: { action } },
    `维保合同已${action}`,
  )
}

async function removeRow(row: Row) {
  if (!window.confirm(`确认删除合同「${row['合同编号']}」？历史履约记录会保留在原服务单位名下。`)) return
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}?${unitQuery()}`, { method: 'DELETE' })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '删除未生效')
    }
    okMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '删除失败'
  }
}

function openCreate() {
  if (isShared(session.serviceUnit)) {
    errorMessage.value = '当前是集团共用服务单位，共用名录只读，不能登记合同，请切换到具体服务单位'
    return
  }
  Object.assign(form, {
    show: true, mode: 'create', title: '登记维保合同',
    desc: `合同归属：${session.serviceUnit}`, id: 0,
    code: '', equipment: '', amount: '', due: '', target: '',
  })
}

function openAdjust(row: Row) {
  Object.assign(form, {
    show: true, mode: 'adjust', title: `调整合同「${row['合同编号']}」`,
    desc: '', id: Number(row.id),
    code: '', equipment: '',
    amount: row['合同金额'] ?? '', due: row['到期日期'] ?? '', target: '',
  })
}

function openTransfer(row: Row) {
  Object.assign(form, {
    show: true, mode: 'transfer', title: `变更合同归属「${row['合同编号']}」`,
    desc: '', id: Number(row.id),
    code: '', equipment: '', amount: '', due: '', target: '',
  })
}

function openClaim(row: Row) {
  openTransfer(row)
  form.title = `认领归属缺失合同「${row['合同编号']}」`
}

function closeForm() {
  form.show = false
}

async function submitForm() {
  if (form.mode === 'create') {
    if (!form.code.trim() || !form.equipment.trim()) {
      errorMessage.value = '合同编号与维保设备为必填项'
      return
    }
    const ok = await postAction(
      `${ENDPOINT}?${unitQuery()}`,
      { values: { 合同编号: form.code.trim(), 维保设备: form.equipment.trim(), 合同金额: Number(form.amount || 0), 到期日期: form.due } },
      '维保合同已登记',
    )
    if (ok) form.show = false
    return
  }
  if (form.mode === 'adjust') {
    const values: Record<string, string | number> = {}
    if (form.amount !== '') values['合同金额'] = Number(form.amount)
    if (form.due) values['到期日期'] = form.due
    if (!Object.keys(values).length) {
      errorMessage.value = '请至少填写一项要调整的合同金额或到期日期'
      return
    }
    try {
      const response = await request(`${ENDPOINT}/${form.id}?${unitQuery()}`, {
        method: 'PATCH',
        body: JSON.stringify({ values }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok || !payload?.ok) throw new Error(payload?.message || '调整未生效')
      okMessage.value = payload.message
      errorMessage.value = ''
      form.show = false
      await reload()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '调整失败'
    }
    return
  }
  if (!form.target) {
    errorMessage.value = '请选择目标服务单位'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${form.id}/owner?${unitQuery()}`, {
      method: 'PUT',
      body: JSON.stringify({ values: { 服务单位: form.target } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) throw new Error(payload?.message || '归属变更未生效')
    okMessage.value = payload.message
    errorMessage.value = ''
    form.show = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '归属变更失败'
  }
}

async function openDetail(row: Row) {
  detail.show = true
  detail.row = row
  detail.history = []
  try {
    const [detailResp, historyResp] = await Promise.all([
      request(`${ENDPOINT}/${row.id}?${unitQuery()}`),
      request(`${ENDPOINT}/${row.id}/history?${unitQuery()}`),
    ])
    const detailPayload = await detailResp.json().catch(() => null)
    if (detailPayload?.ok) detail.row = detailPayload.entry
    else errorMessage.value = detailPayload?.message || '合同详情读取失败'
    const historyPayload = await historyResp.json().catch(() => null)
    detail.history = historyPayload?.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '合同详情读取失败'
  }
}

function exportRows() {
  window.open(`${ENDPOINT}/export?${unitQuery(`scope=${scope.value}`)}`, '_blank')
}

onMounted(async () => {
  await loadUnits()
  await reload()
})
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; align-items: flex-end; }
.unit-pick span { display: block; font-size: 12px; color: var(--muted); }
.unit-pick select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.scope-tabs { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.scope-tab { border: 1px solid var(--border); background: #fff; border-radius: 6px; padding: 6px 12px; cursor: pointer; font-size: 13px; }
.scope-tab.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.tab-badge { display: inline-block; margin-left: 4px; background: #b42318; color: #fff; border-radius: 10px; padding: 0 6px; font-size: 11px; }
.scope-hint { color: var(--muted); font-size: 12px; }
.status-tag { border-radius: 10px; padding: 2px 8px; font-size: 12px; }
.status-tag.running { background: #e7f6ec; color: #117a37; }
.status-tag.expired { background: #fdecec; color: #b42318; }
.status-tag.stopped { background: #eef0f3; color: #475467; }
.status-tag.draft { background: #fff4e0; color: #b54708; }
.scope-tag { border-radius: 4px; padding: 1px 6px; font-size: 12px; }
.scope-tag.own { background: #e7f0fe; color: #1f6feb; }
.scope-tag.shared { background: #f3edff; color: #6941c6; }
.scope-tag.missing { background: #fdecec; color: #b42318; }
.scope-tag.other { background: #eef0f3; color: #475467; }
.readonly-note { color: var(--muted); font-size: 12px; }
.link.danger { color: #b42318; }
.ok-text { color: #117a37; }
.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 420px; max-height: 86vh; overflow: auto; }
.modal.wide { width: 720px; }
.modal h3 { margin: 0 0 10px; font-size: 16px; }
.modal h4 { margin: 14px 0 6px; font-size: 14px; }
.modal-desc { color: var(--muted); font-size: 12px; margin: 6px 0; }
.form-line { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; font-size: 13px; }
.form-line input, .form-line select { flex: 1; max-width: 240px; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; }
.detail-item { display: flex; flex-direction: column; gap: 2px; background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 12px; }
.detail-item em { color: var(--muted); font-style: normal; }
.detail-item strong { font-weight: 600; }
.history-table th, .history-table td { font-size: 12px; }
</style>
