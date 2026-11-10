import { ref, watch } from 'vue'
import { dictApi } from '../api'

// 同一项目的字典项在一次会话里反复用到,做一层短缓存避免每个页面各发一次请求
const cache = new Map()
const TTL = 60000

export async function loadEffectiveDict(projectId, force = false) {
  const cacheKey = projectId || 0
  const hit = cache.get(cacheKey)
  if (hit && !force && Date.now() - hit.ts < TTL) {
    return hit.data
  }
  // 不传项目 = 全局口径,用于"全部项目"这类跨项目筛选
  const data = await dictApi.effective(projectId ? { project_id: projectId } : {})
  cache.set(cacheKey, { ts: Date.now(), data })
  return data
}

export function clearDictCache(projectId) {
  cache.delete(projectId || 0)
}

/** 全局字典项变动会影响所有项目的有效值,需要整表失效 */
export function clearAllDictCache() {
  cache.clear()
}

/**
 * 按项目取字典选项:下拉框、标签色都从这里出,页面不再写死枚举值。
 * projectIdOrRef 传 ref/computed 时会自动跟随切换并刷新。
 */
export function useDict(projectIdOrRef) {
  const entries = ref({})

  async function reload(force = false) {
    const pid = typeof projectIdOrRef === 'object' && projectIdOrRef !== null && 'value' in projectIdOrRef
      ? projectIdOrRef.value
      : projectIdOrRef
    try {
      entries.value = await loadEffectiveDict(pid, force)
    } catch (e) {
      entries.value = {}
    }
  }

  if (typeof projectIdOrRef === 'object' && projectIdOrRef !== null && 'value' in projectIdOrRef) {
    watch(projectIdOrRef, () => reload(), { immediate: true })
  } else {
    reload()
  }

  const list = (key) => entries.value[key] || []
  const labels = (key) => list(key).map((o) => o.label)
  const tagType = (key, label) => list(key).find((o) => o.label === label)?.color || 'info'
  const isUrgent = (key, label) => !!list(key).find((o) => o.label === label)?.is_urgent
  /** 表单默认值:优先用约定俗成的 preferred,该值被改名或停用后退到首个启用项 */
  const pick = (key, preferred = '') => {
    const items = list(key)
    if (!items.length) return preferred
    const hit = items.find((o) => o.label === preferred)
    return hit ? hit.label : items[0].label
  }

  return { entries, list, labels, tagType, isUrgent, pick, reload }
}
