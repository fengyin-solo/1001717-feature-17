import { defineStore } from 'pinia'

/** 当前值班会话：operator 是展示名，serviceUnit 是履约可见范围的单位编码。 */
type UnitOption = { code: string; name: string }

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '特种设备点检运维平台',
    serviceUnit: 'unit-1',
    unitName: '一车间',
    units: [
      { code: 'unit-1', name: '一车间' },
      { code: 'unit-2', name: '二车间' },
      { code: 'unit-3', name: '三车间' },
    ] as UnitOption[],
    sharedUnit: { code: 'shared', name: '共用服务单位' },
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setServiceUnit(code: string) {
      const match = this.units.find((item) => item.code === code)
      if (!match) return
      this.serviceUnit = match.code
      this.unitName = match.name
    },
    unitLabel(code?: string | null): string {
      if (!code) return '归属缺失'
      if (code === this.sharedUnit.code) return this.sharedUnit.name
      return this.units.find((item) => item.code === code)?.name ?? code
    },
  },
})
