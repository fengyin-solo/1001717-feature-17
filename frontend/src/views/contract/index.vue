<template>
  <section class="page" data-module="contract">
    <header class="page-head">
      <div>
        <h2>维保合同管理</h2>
        <p class="page-desc">
          合同按服务单位归属：{{ session.unitName }}只能查看和维护本单位合同，
          「共用服务单位」合同只读，归属缺失合同需先认领。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记维保合同</button>
        <button class="btn" type="button" @click="exportRows">导出可见合同清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card" :class="{ warn: item.warn }">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <nav class="scope-tabs">
      <button
        v-for="tab in scopeTabs"
        :key="tab.value"
        type="button"
        class="scope-tab"
        :class="{ active: scope === tab.value }"
        @click="switchScope(tab.value)"
      >
        {{ tab.label }}
        <span class="scope-count" v-if="tab.value !== 'all_visible'">{{ scopeCounts[tab.value] ?? 0 }}</span>
      </button>
    </nav>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>合同编号</span>
        <input v-model="keyword" placeholder="按合同编号检索" />
      </label>
      <label class="filter-item">
        <span>履约状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="scope === 'shared'" class="scope-hint">共用服务单位的合同各单位只读查看，不能登记履约、改金额或做状态流转。</p>
    <p v-else-if="scope === 'missing'" class="scope-hint warn-text">
      以下合同缺少归属服务单位，不计入任何单位的在履统计；由本单位认领补录归属后方可维护。
    </p>
    <p v-else-if="scope === 'legacy'" class="scope-hint">
      以下合同已转出至其他服务单位，本单位只能只读查看；归属变更前产生的历史履约记录仍留在本单位名下。
    </p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>履约状态</th>
          <th>可执行操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-readonly': row.readonly && scope !== 'mine' }">
          <td>{{ row['合同编号'] ?? '—' }}</td>
          <td>
            {{ row['归属单位'] ?? '归属缺失' }}
            <span v-if="row.scope === 'shared'" class="tag tag-muted">共用只读</span>
            <span v-else-if="row.scope === 'legacy'" class="tag tag-legacy">已转出</span>
            <span v-else-if="row.scope === 'missing'" class="tag tag-warn">待认领</span>
          </td>
          <td>{{ row['维保设备'] ?? '—' }}</td>
          <td>{{ row['合同金额'] ?? '—' }}</td>
          <td>{{ row['服务期限'] ?? '—' }}</td>
          <td>{{ row['签订人员'] ?? '—' }}</td>
          <td>{{ row['到期日期'] ?? '—' }}</td>
          <td><span class="tag" :class="statusTagClass(row.status)">{{ row.status }}</span></td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <template v-if="row.scope === 'mine'">
              <button class="link" type="button" @click="openEdit(row)">编辑</button>
              <button
                v-for="action in availableActions(row.status)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <button class="link" type="button" @click="openTransfer(row)">归属变更</button>
              <button class="link link-danger" type="button" @click="removeRow(row)">删除</button>
            </template>
            <button v-else-if="row.scope === 'missing'" class="link" type="button" @click="claimRow(row)">本单位认领</button>
            <span v-else class="readonly-text">{{ row.scope === 'legacy' ? '已转出·只读' : '只读' }}</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条合同记录（{{ scopeLabel }}，当前归属视角：{{ session.unitName }}）</span>
      <span v-if="message" :class="messageTone">{{ message }}</span>
    </footer>

    <!-- 合同详情：履约状态与列表同源；含归属变更流水与本单位可见的履约记录 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <h3>合同详情 · {{ detail['合同编号'] }}</h3>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </template>
          <dt>归属单位</dt>
          <dd>{{ detail['归属单位'] ?? '归属缺失' }}</dd>
          <dt>履约状态</dt>
          <dd><span class="tag" :class="statusTagClass(detail.status)">{{ detail.status }}</span></dd>
        </dl>
        <h4>履约记录（结算单）</h4>
        <table class="data-table inner-table">
          <thead>
            <tr><th>结算单号</th><th>履约单位</th><th>结算状态</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in detail['履约记录']" :key="idx">
              <td>{{ item['结算单号'] }}</td>
              <td>{{ item['履约单位'] || '—' }}</td>
              <td>{{ item['结算状态'] }}</td>
            </tr>
            <tr v-if="!detail['履约记录']?.length">
              <td colspan="3" class="empty-state">本单位名下暂无履约记录；归属变更前他单位的历史记录仍留在原单位</td>
            </tr>
          </tbody>
        </table>
        <h4>归属变更记录</h4>
        <ul class="log-list">
          <li v-for="(item, idx) in detail['归属变更']" :key="idx">
            {{ item['变更日期'] }}：{{ item['操作单位'] }} 发起，{{ item['原归属'] || '归属缺失' }} → {{ item['新归属'] }}
          </li>
          <li v-if="!detail['归属变更']?.length" class="muted">暂无归属变更</li>
        </ul>
        <div class="modal-foot">
          <button class="btn" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 登记 / 编辑：服务单位不允许在表单里改，归属只能走「归属变更」 -->
    <div v-if="formOpen" class="modal-mask" @click.self="formOpen = false">
      <div class="modal">
        <h3>{{ formMode === 'create' ? '登记维保合同' : `编辑合同 · ${formState['合同编号']}` }}</h3>
        <div class="form-grid">
          <label v-for="field in formFields" :key="field" class="form-item">
            <span>{{ field }}<em v-if="requiredFields.includes(field)">*</em></span>
            <input v-model="formState[field]" :placeholder="`请输入${field}`" />
          </label>
          <label class="form-item">
            <span>归属服务单位</span>
            <input :value="session.unitName" disabled />
          </label>
        </div>
        <p class="form-tip">新登记合同自动归属{{ session.unitName }}；调整合同金额或到期日期后，履约状态将自动重新判定。</p>
        <div class="modal-foot">
          <button class="btn" type="button" @click="formOpen = false">取消</button>
          <button class="btn primary" type="button" @click="submitForm">保存</button>
        </div>
      </div>
    </div>

    <!-- 归属变更：仅本单位合同可发起，历史履约记录保留在原单位 -->
    <div v-if="transferOpen" class="modal-mask" @click.self="transferOpen = false">
      <div class="modal">
        <h3>归属变更 · {{ transferRow?.['合同编号'] }}</h3>
        <p class="form-tip">
          当前归属：{{ transferRow?.['归属单位'] }}。变更后合同由接收单位维护，
          变更前的历史履约记录仍留在「{{ transferRow?.['归属单位'] }}」名下；共用档案不能作为接收方。
        </p>
        <label class="form-item">
          <span>接收服务单位<em>*</em></span>
          <select v-model="transferTarget">
            <option value="" disabled>请选择接收单位</option>
            <option
              v-for="unit in transferOptions"
              :key="unit.code"
              :value="unit.code"
            >{{ unit.name }}</option>
          </select>
        </label>
        <div class="modal-foot">
          <button class="btn" type="button" @click="transferOpen = false">取消</button>
          <button class="btn primary" type="button" @click="submitTransfer">确认变更</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { postAction, request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, any>

const ENDPOINT = '/api/contract'
const session = useSessionStore()

const columns = ['合同编号', '服务单位', '维保设备', '合同金额', '服务期限', '签订人员', '到期日期']
const detailFields = columns.filter((field) => field !== '服务单位')
const statuses = ['待签订', '履行中', '已到期', '已终止']
const scopeTabs = [
  { value: 'mine', label: '本单位合同' },
  { value: 'shared', label: '共用合同（只读）' },
  { value: 'missing', label: '归属缺失' },
  { value: 'legacy', label: '已转出留档' },
  { value: 'all_visible', label: '全部可见' },
] as const

const rows = ref<Row[]>([])
const total = ref(0)
const scope = ref<string>('mine')
const keyword = ref('')
const statusFilter = ref('')
const message = ref('')
const messageTone = ref('muted')
const scopeCounts = ref<Record<string, number>>({ mine: 0, shared: 0, missing: 0 })
const summary = ref<Record<string, number>>({})

const scopeLabel = computed(() => scopeTabs.find((tab) => tab.value === scope.value)?.label ?? '')
const emptyText = computed(() => {
  if (scope.value === 'shared') return '暂无共用服务单位合同'
  if (scope.value === 'missing') return '没有归属缺失的合同，口径已齐'
  if (scope.value === 'legacy') return '没有从本单位转出的合同'
  if (scope.value === 'all_visible') return '当前视角下暂无可见合同'
  return `${session.unitName}名下暂无维保合同，可先登记`
})
const statCards = computed(() => [
  { label: `本单位在履合同（${session.unitName}）`, value: summary.value['在履合同'] ?? 0 },
  { label: '本单位合同总数', value: summary.value['本单位合同'] ?? 0 },
  { label: '30天内到期', value: summary.value['临近到期'] ?? 0, warn: (summary.value['临近到期'] ?? 0) > 0 },
  { label: '共用只读合同', value: summary.value['共用合同'] ?? 0 },
  { label: '归属缺失', value: summary.value['归属缺失'] ?? 0, warn: (summary.value['归属缺失'] ?? 0) > 0 },
  { label: '本单位合同总金额', value: summary.value['合同总金额'] ?? 0 },
])

// ---- 详情 / 表单 / 归属变更弹窗状态 ----
const detail = ref<Row | null>(null)
const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingId = ref<number | null>(null)
const formFields = ['合同编号', '维保设备', '合同金额', '服务期限', '签订人员', '到期日期']
const requiredFields = ['合同编号', '维保设备']
const formState = ref<Record<string, string>>({})
const transferOpen = ref(false)
const transferRow = ref<Row | null>(null)
const transferTarget = ref('')
const transferOptions = computed(() =>
  session.units.filter((unit) => unit.name !== transferRow.value?.['归属单位']),
)

function availableActions(currentStatus: string): string[] {
  // 动作按当前履约状态收敛，避免对已终止合同重复操作。
  if (currentStatus === '已终止') return []
  if (currentStatus === '已到期') return ['终止合同']
  if (currentStatus === '履行中') return ['标记到期', '终止合同']
  return ['确认签订']
}

function statusTagClass(status?: string): string {
  return {
    待签订: 'tag-muted',
    履行中: 'tag-active',
    已到期: 'tag-expired',
    已终止: 'tag-terminated',
  }[status ?? ''] ?? 'tag-muted'
}

function notify(text: string, ok = true) {
  message.value = text
  messageTone.value = ok ? 'muted' : 'error-text'
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function switchScope(next: string) {
  scope.value = next
  message.value = ''
  void reload()
}

async function reload() {
  message.value = ''
  const params = new URLSearchParams({ scope: scope.value, page: '1', size: '200' })
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) throw new Error('维保合同列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    notify(error instanceof Error ? error.message : '维保合同列表读取失败', false)
  }
  void loadSummaryAndCounts()
}

async function loadSummaryAndCounts() {
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (response.ok) summary.value = await response.json()
  } catch {
    /* 概览数字拉取失败不阻塞列表 */
  }
  // 各范围数量单独取，保证页签角标与列表、概览是同一套归属口径。
  await Promise.all(
    (['mine', 'shared', 'missing', 'legacy'] as const).map(async (key) => {
      try {
        const response = await request(`${ENDPOINT}?scope=${key}&page=1&size=1`)
        if (response.ok) {
          scopeCounts.value[key] = (await response.json()).total
        }
      } catch {
        /* ignore */
      }
    }),
  )
}

async function openDetail(row: Row) {
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(body?.detail ?? '合同详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    notify(error instanceof Error ? error.message : '合同详情读取失败', false)
  }
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = null
  formState.value = Object.fromEntries(formFields.map((field) => [field, '']))
  formOpen.value = true
}

function openEdit(row: Row) {
  formMode.value = 'edit'
  editingId.value = Number(row.id)
  formState.value = Object.fromEntries(formFields.map((field) => [field, String(row[field] ?? '')]))
  formOpen.value = true
}

async function submitForm() {
  const missing = requiredFields.filter((field) => !formState.value[field]?.trim())
  if (missing.length) {
    notify(`缺少必填字段：${missing.join('、')}`, false)
    return
  }
  try {
    let response: Response
    if (formMode.value === 'create') {
      response = await request(ENDPOINT, {
        method: 'POST',
        body: JSON.stringify({ values: { ...formState.value } }),
      })
    } else {
      response = await request(`${ENDPOINT}/${editingId.value}`, {
        method: 'PUT',
        body: JSON.stringify({ values: { ...formState.value } }),
      })
    }
    const body = await response.json()
    if (!response.ok || body.ok === false) {
      notify(body.detail || body.message || '保存未生效', false)
      return
    }
    notify(body.message || '已保存')
    formOpen.value = false
    await reload()
  } catch (error) {
    notify(error instanceof Error ? error.message : '保存失败', false)
  }
}

async function runAction(action: string, row: Row) {
  const result = await postAction(`${ENDPOINT}/${row.id}/actions`, { action })
  notify(result.message, result.ok)
  if (result.ok) await reload()
}

function openTransfer(row: Row) {
  transferRow.value = row
  transferTarget.value = ''
  transferOpen.value = true
}

async function submitTransfer() {
  if (!transferTarget.value) {
    notify('请选择接收的服务单位', false)
    return
  }
  const result = await postAction(`${ENDPOINT}/${transferRow.value?.id}/transfer`, {
    目标单位: transferTarget.value,
  })
  notify(result.message, result.ok)
  if (result.ok) {
    transferOpen.value = false
    await reload()
  }
}

async function claimRow(row: Row) {
  const result = await postAction(`${ENDPOINT}/${row.id}/claim`, {})
  notify(result.message, result.ok)
  if (result.ok) await reload()
}

async function removeRow(row: Row) {
  const confirmed = window.confirm(
    `确认删除合同「${row['合同编号']}」？已被履约结算引用的合同将被拦下。`,
  )
  if (!confirmed) return
  try {
    const response = await request(`${ENDPOINT}/${row.id}`, { method: 'DELETE' })
    const body = await response.json()
    notify(body.message, body.ok)
    if (body.ok) await reload()
  } catch (error) {
    notify(error instanceof Error ? error.message : '删除失败', false)
  }
}

function exportRows() {
  // 导出同样带当前单位视角（请求拦截器会补头），他单位合同不会出现在文件里。
  const url = `${ENDPOINT}/export?scope=${scope.value === 'mine' ? 'all_visible' : scope.value}`
  void request(url).then(async (response) => {
    if (!response.ok) {
      notify('导出失败：可见范围校验未通过', false)
      return
    }
    const blob = await response.blob()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `维保合同-${session.unitName}-${scope.value}.json`
    link.click()
    URL.revokeObjectURL(link.href)
  })
}

function onUnitChanged() {
  message.value = ''
  detail.value = null
  void reload()
}

onMounted(() => {
  void reload()
  window.addEventListener('service-unit-changed', onUnitChanged)
})
onUnmounted(() => window.removeEventListener('service-unit-changed', onUnitChanged))
</script>

<style scoped>
.scope-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.scope-tab { border: 1px solid var(--border); background: #fff; border-radius: 6px 6px 0 0; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.scope-tab.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.scope-count { display: inline-block; min-width: 18px; margin-left: 6px; padding: 0 5px; border-radius: 9px; background: #eef2f7; color: var(--muted); font-size: 12px; }
.scope-tab.active .scope-count { background: rgba(255, 255, 255, 0.25); color: #fff; }
.scope-hint { margin: 0 0 10px; font-size: 13px; color: var(--muted); }
.warn-text, .warn .stat-value { color: #b42318; }
.row-readonly { background: #fafbfc; }
.readonly-text { color: var(--muted); font-size: 12px; }
.link-danger { color: #b42318; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; }
.tag-muted { background: #eef2f7; color: var(--muted); }
.tag-active { background: #e7f6ec; color: #1a7f37; }
.tag-expired { background: #fdf1e3; color: #b54708; }
.tag-terminated { background: #fde8e8; color: #b42318; }
.tag-warn { margin-left: 6px; background: #fde8e8; color: #b42318; }
.tag-legacy { margin-left: 6px; background: #eef2ff; color: #3949ab; }
.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #fff; border-radius: 10px; width: 720px; max-width: 92vw; max-height: 86vh; overflow: auto; padding: 18px 20px; }
.modal h3 { margin: 0 0 12px; font-size: 16px; }
.modal h4 { margin: 14px 0 6px; font-size: 14px; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.detail-grid { display: grid; grid-template-columns: 110px 1fr 110px 1fr; gap: 6px 10px; margin: 0; font-size: 13px; }
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.inner-table { margin: 6px 0; }
.log-list { margin: 0; padding-left: 18px; font-size: 13px; color: #374151; }
.log-list .muted { color: var(--muted); list-style: none; margin-left: -18px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
.form-item { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-item em { color: #b42318; font-style: normal; margin-left: 2px; }
.form-item input, .form-item select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; color: #1f2937; }
.form-item input:disabled { background: #f1f5f9; color: var(--muted); }
.form-tip { font-size: 12px; color: var(--muted); margin: 10px 0 0; }
.muted { color: var(--muted); }
</style>
