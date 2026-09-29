import { defineStore } from 'pinia'

// 默认以内聚的业务单位登录，可在维保合同页切换归属视角
const DEFAULT_UNIT = '华东维保站'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '特种设备点检运维平台',
    serviceUnit: DEFAULT_UNIT,
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setServiceUnit(unit: string) {
      this.serviceUnit = unit
    },
  },
})
