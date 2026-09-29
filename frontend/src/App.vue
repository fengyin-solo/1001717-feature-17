<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">特种设备点检运维平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向锅炉、压力容器、起重机械、电梯等特种设备的台账建档、日常点检、润滑保养、定期检验与隐患整改的一体化运维后台。</span>
        <span class="head-user">
          当前值班：{{ store.operator }} · {{ store.shiftLabel }}
          <label class="unit-switch">
            履约归属视角
            <select :value="store.serviceUnit" @change="switchUnit(($event.target as HTMLSelectElement).value)">
              <option v-for="unit in store.units" :key="unit.code" :value="unit.code">{{ unit.name }}</option>
            </select>
          </label>
        </span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "锅炉设备", path: "/boiler" }, { label: "压力容器", path: "/vessel" }, { label: "压力管道", path: "/pressurepipe" }, { label: "起重机械", path: "/crane" }, { label: "电梯设备", path: "/elevator" }, { label: "场内机动车辆", path: "/forklift" }, { label: "点检计划", path: "/plan" }, { label: "点检记录", path: "/spotcheck" }, { label: "润滑保养", path: "/lubricate" }, { label: "定期检验", path: "/inspect" }, { label: "检验报告", path: "/report" }, { label: "隐患登记", path: "/hazard" }, { label: "整改闭环", path: "/rectify" }, { label: "使用登记", path: "/register" }, { label: "作业人员", path: "/operator" }, { label: "备件器材", path: "/spare" }, { label: "维保合同", path: "/contract" }, { label: "费用结算", path: "/settle" }]

function switchUnit(code: string) {
  // 切换后所有页面重新请求；单位头由请求封装统一带上，列表/详情/概览口径随之刷新。
  store.setServiceUnit(code)
  window.dispatchEvent(new CustomEvent('service-unit-changed'))
}
</script>

<style scoped>
.unit-switch { display: inline-flex; align-items: center; gap: 6px; margin-left: 12px; }
.unit-switch select { padding: 2px 6px; border-radius: 4px; border: 1px solid var(--border); }
</style>
