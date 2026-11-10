<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dictApi, projectApi } from '../api'
import { useAuthStore } from '../stores/auth'
import { clearAllDictCache, clearDictCache } from '../composables/useDict'

const auth = useAuthStore()
const COLORS = [
  { label: '红色', value: 'danger' },
  { label: '橙色', value: 'warning' },
  { label: '蓝色', value: 'primary' },
  { label: '绿色', value: 'success' },
  { label: '灰色', value: 'info' },
]

const loading = ref(false)
const saving = ref(false)
const types = ref({ configurable: [], locked: [] })
const projects = ref([])
const items = ref([])
const scope = reactive({ mode: 'project', project_id: null })
const activeKey = ref('case_priority')

const activeType = computed(() => types.value.configurable.find((t) => t.key === activeKey.value) || {})
const canEditGlobal = computed(() => auth.role === 'admin')
const canEdit = computed(() => (scope.mode === 'global' ? canEditGlobal.value : !!scope.project_id))

const dialogVisible = ref(false)
const editingId = ref(null)
const editingBuiltin = ref(false)
const form = reactive({ label: '', color: 'info', sort_order: 0, enabled: true, is_urgent: false, remark: '' })

function invalidate() {
  // 全局项变动会改变所有项目的有效值,项目项只影响本项目
  if (scope.mode === 'global') clearAllDictCache()
  else clearDictCache(scope.project_id)
}

async function loadItems() {
  if (!activeKey.value) return
  if (scope.mode === 'project' && !scope.project_id) {
    items.value = []
    return
  }
  loading.value = true
  try {
    const params = { dict_key: activeKey.value }
    if (scope.mode === 'project') params.project_id = scope.project_id
    items.value = await dictApi.list(params)
  } finally {
    loading.value = false
  }
}

async function loadProjects() {
  projects.value = await projectApi.list()
  if (!scope.project_id && projects.value.length) {
    scope.project_id = projects.value[0].id
  }
}

function sourceLabel(row) {
  if (row.source === 'project') return '本项目'
  if (row.builtin) return '内置'
  return '全局默认'
}

function openCreate() {
  editingId.value = null
  editingBuiltin.value = false
  Object.assign(form, {
    label: '', color: 'info',
    sort_order: (items.value.length ? items.value[items.value.length - 1].sort_order : 0) + 1,
    enabled: true, is_urgent: false, remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  editingBuiltin.value = !!row.builtin
  Object.assign(form, {
    label: row.label, color: row.color || 'info', sort_order: row.sort_order,
    enabled: row.enabled, is_urgent: row.is_urgent, remark: row.remark || '',
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.label.trim()) {
    ElMessage.error('请填写选项名称')
    return
  }
  saving.value = true
  try {
    const payload = { ...form, label: form.label.trim() }
    if (!activeType.value.has_urgent) delete payload.is_urgent
    if (editingId.value) {
      await dictApi.update(editingId.value, payload)
    } else {
      await dictApi.create({
        dict_key: activeKey.value,
        project_id: scope.mode === 'project' ? scope.project_id : null,
        ...payload,
      })
    }
    dialogVisible.value = false
    ElMessage.success('已保存')
    invalidate()
    await loadItems()
  } finally {
    saving.value = false
  }
}

async function toggle(row) {
  try {
    await dictApi.update(row.id, { enabled: row.enabled })
    invalidate()
    ElMessage.success(row.enabled ? '已启用' : '已停用')
  } catch (e) {
    row.enabled = !row.enabled
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除选项「${row.label}」?`, '提示', { type: 'warning' })
  await dictApi.remove(row.id)
  invalidate()
  ElMessage.success('已删除')
  await loadItems()
}

watch(() => [scope.mode, scope.project_id], loadItems)
watch(activeKey, loadItems)

onMounted(async () => {
  types.value = await dictApi.types()
  await loadProjects()
  if (scope.mode === 'project' && !scope.project_id) {
    scope.mode = 'global'
  }
  await loadItems()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h2>数据字典</h2>
      <el-button type="primary" @click="openCreate" :disabled="!canEdit">新增选项</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 14px"
      title="用例优先级、缺陷严重程度等枚举值在这里维护。项目级选项覆盖同名全局选项,停用只影响新写入,历史数据仍可原样查看和编辑。内置选项不可改名、不可删除,需要换名请在项目基础上新增。"
    />

    <el-card v-loading="loading">
      <el-form :inline="true" style="margin-bottom: 6px">
        <el-form-item label="范围">
          <el-radio-group v-model="scope.mode">
            <el-radio-button value="project">项目</el-radio-button>
            <el-radio-button value="global" :disabled="!canEditGlobal">全局默认</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="scope.mode === 'project'" label="项目">
          <el-select v-model="scope.project_id" style="width: 220px">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-tabs v-model="activeKey">
        <el-tab-pane v-for="t in types.configurable" :key="t.key" :label="t.name" :name="t.key">
          <div style="color: #909399; font-size: 12px; margin-bottom: 8px">
            {{ t.mode === 'validate' ? '严格校验:业务数据只能填下列启用值' : '建议取值:可自由填写,这里只提供候选' }}
            · 内置值: {{ t.defaults.join(' / ') }}
          </div>
          <el-table :data="items.filter((r) => r.dict_key === t.key)" border stripe>
            <el-table-column label="选项" min-width="140">
              <template #default="{ row }">
                <el-tag :type="row.color || 'info'" size="small">{{ row.label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="色值" width="110">
              <template #default="{ row }">{{ row.color || '默认' }}</template>
            </el-table-column>
            <el-table-column prop="sort_order" label="排序" width="80" />
            <el-table-column v-if="t.has_urgent" label="计入紧急" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.is_urgent" type="danger" size="small">是</el-tag>
                <span v-else style="color: #c0c4cc">否</span>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="80">
              <template #default="{ row }">
                <el-switch v-model="row.enabled" :disabled="!canEdit || !row.id" @change="toggle(row)" />
              </template>
            </el-table-column>
            <el-table-column label="来源" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.source === 'project' ? 'success' : (row.builtin ? 'info' : 'warning')" effect="plain">
                  {{ sourceLabel(row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="140" />
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" :disabled="!canEdit || !row.id" @click="openEdit(row)">编辑</el-button>
                <el-button link type="danger" :disabled="!canEdit || !row.id || row.builtin" @click="remove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-card style="margin-top: 14px">
      <template #header>固定口径(不可配置)</template>
      <el-table :data="types.locked" border>
        <el-table-column prop="name" label="口径" width="160" />
        <el-table-column label="取值" min-width="260">
          <template #default="{ row }">
            <el-tag v-for="v in row.values" :key="v" size="small" style="margin-right: 6px">{{ v }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="为什么不开放配置" min-width="280" />
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑选项' : '新增选项'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="字典类型">
          <el-input :model-value="activeType.name" disabled />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.label" :disabled="editingBuiltin" :placeholder="editingBuiltin ? '内置选项不能改名' : ''" />
        </el-form-item>
        <el-form-item label="标签色">
          <el-select v-model="form.color" style="width: 160px">
            <el-option v-for="c in COLORS" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
          <el-tag :type="form.color" size="small" style="margin-left: 10px">{{ form.label || '预览' }}</el-tag>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
        </el-form-item>
        <el-form-item v-if="activeType.has_urgent" label="计入紧急">
          <el-switch v-model="form.is_urgent" />
          <span style="margin-left: 10px; color: #909399; font-size: 12px">勾选后该值按紧急口径推送通知</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.page-header h2 {
  margin: 0;
  font-size: 20px;
  margin-right: auto;
}
</style>
