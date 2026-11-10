<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { gateApi, projectApi, templateApi, dictApi } from '../api'
import { useAuthStore } from '../stores/auth'
import { clearDictCache } from '../composables/useDict'

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')
const STAGES = ['SIT', 'UAT', 'PRE']
const KINDS = ['准入', '准出']
const FIELD_TYPES = [
  { label: '文本', value: 'text' },
  { label: '下拉', value: 'select' },
  { label: '数字', value: 'number' },
  { label: '日期', value: 'date' },
]
const COLORS = ['danger', 'warning', 'primary', 'success', 'info']
const stageLabel = (s) => (s === 'PRE' ? '预发版' : s)

const loading = ref(false)
const saving = ref(false)
const templates = ref([])
const projects = ref([])
const rules = ref([])
const dictTypes = ref([])

const dialogVisible = ref(false)
const editingId = ref(null)
const activeTab = ref('basic')
const form = reactive({
  name: '', description: '', is_default: false,
  stage_days: { SIT: 10, UAT: 5, PRE: 2 },
  gates: [], custom_fields: [], tags: [], dict_items: [],
})

const applyVisible = ref(false)
const applyForm = reactive({ tpl_id: null, project_id: null })
const collectVisible = ref(false)
const savingFrom = ref(null)

async function load() {
  loading.value = true
  try {
    templates.value = await templateApi.list()
  } finally {
    loading.value = false
  }
}

async function loadRefs() {
  projects.value = await projectApi.list()
  rules.value = await gateApi.rules()
  dictTypes.value = (await dictApi.types()).configurable
}

function blank() {
  Object.assign(form, {
    name: '', description: '', is_default: false,
    stage_days: { SIT: 10, UAT: 5, PRE: 2 },
    gates: [], custom_fields: [], tags: [], dict_items: [],
  })
}

function openCreate() {
  editingId.value = null
  activeTab.value = 'basic'
  blank()
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  activeTab.value = 'basic'
  Object.assign(form, {
    name: row.name, description: row.description, is_default: row.is_default,
    stage_days: { SIT: 10, UAT: 5, PRE: 2, ...(row.stage_days || {}) },
    gates: (row.gates || []).map((g) => ({ ...g })),
    custom_fields: (row.custom_fields || []).map((f) => ({ ...f, options_text: (f.options || []).join(',') })),
    tags: (row.tags || []).map((t) => ({ ...t })),
    dict_items: (row.dict_items || []).map((d) => ({ ...d })),
  })
  dialogVisible.value = true
}

function addGate() {
  form.gates.push({ stage: 'SIT', kind: '准出', rule: 'pass_rate_min', threshold: 95, enabled: true })
}

function addField() {
  form.custom_fields.push({ name: '', field_type: 'text', options_text: '', required: false, sort_order: form.custom_fields.length + 1 })
}

function addTag() {
  form.tags.push({ name: '', color: '#409EFF' })
}

function addDictItem() {
  form.dict_items.push({ dict_key: 'case_priority', label: '', color: 'info', sort_order: 0, is_urgent: false })
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.error('请填写模板名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description,
      is_default: form.is_default,
      stage_days: Object.fromEntries(
        STAGES.filter((s) => Number(form.stage_days[s]) > 0).map((s) => [s, Number(form.stage_days[s])])
      ),
      gates: form.gates.map((g) => ({ stage: g.stage, kind: g.kind, rule: g.rule, threshold: Number(g.threshold), enabled: !!g.enabled })),
      custom_fields: form.custom_fields.filter((f) => f.name.trim()).map((f, i) => ({
        name: f.name.trim(), field_type: f.field_type, required: !!f.required, sort_order: i + 1,
        options: f.field_type === 'select' ? String(f.options_text || '').split(/[,，]/).map((x) => x.trim()).filter(Boolean) : [],
      })),
      tags: form.tags.filter((t) => t.name.trim()).map((t) => ({ name: t.name.trim(), color: t.color })),
      dict_items: form.dict_items.filter((d) => d.label.trim()).map((d, i) => ({
        dict_key: d.dict_key, label: d.label.trim(), color: d.color, sort_order: d.sort_order || i + 1,
        is_urgent: !!d.is_urgent, enabled: d.enabled !== false,
      })),
    }
    if (editingId.value) {
      await templateApi.update(editingId.value, payload)
    } else {
      await templateApi.create(payload)
    }
    dialogVisible.value = false
    ElMessage.success('已保存')
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除模板「${row.name}」?`, '提示', { type: 'warning' })
  await templateApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

function openApply(row) {
  applyForm.tpl_id = row.id
  applyForm.project_id = projects.value.length ? projects.value[0].id : null
  applyVisible.value = true
}

async function doApply() {
  if (!applyForm.project_id) {
    ElMessage.error('请选择项目')
    return
  }
  saving.value = true
  try {
    const res = await templateApi.apply(applyForm.tpl_id, applyForm.project_id)
    applyVisible.value = false
    clearDictCache(applyForm.project_id)
    ElMessage.success(
      `已套用: 门禁+${res.gates} 字段+${res.custom_fields} 标签+${res.tags} 字典+${res.dict_items},跳过重复 ${res.skipped} 项`
    )
  } finally {
    saving.value = false
  }
}

async function openCollect() {
  if (!projects.value.length) {
    ElMessage.error('暂无可用项目')
    return
  }
  savingFrom.value = projects.value[0].id
  collectVisible.value = true
}

async function loadDraft() {
  if (!savingFrom.value) {
    ElMessage.error('请选择项目')
    return
  }
  const draft = await templateApi.collect(savingFrom.value)
  editingId.value = null
  activeTab.value = 'basic'
  Object.assign(form, {
    name: draft.name, description: draft.description, is_default: false,
    stage_days: { SIT: 10, UAT: 5, PRE: 2, ...(draft.stage_days || {}) },
    gates: (draft.gates || []).map((g) => ({ ...g })),
    custom_fields: (draft.custom_fields || []).map((f) => ({ ...f, options_text: (f.options || []).join(',') })),
    tags: (draft.tags || []).map((t) => ({ ...t })),
    dict_items: (draft.dict_items || []).map((d) => ({ ...d })),
  })
  collectVisible.value = false
  dialogVisible.value = true
}

function summary(row) {
  return `${(row.gates || []).length} 门禁 / ${(row.custom_fields || []).length} 字段 / ${(row.tags || []).length} 标签 / ${(row.dict_items || []).length} 字典`
}

function daysText(row) {
  const d = row.stage_days || {}
  return STAGES.filter((s) => d[s]).map((s) => `${s} ${d[s]}天`).join(' · ') || '跟随全局'
}

onMounted(async () => {
  await load()
  await loadRefs()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h2>项目模板</h2>
      <el-button @click="openCollect">从现有项目另存为模板</el-button>
      <el-button v-if="isAdmin" type="primary" @click="openCreate">新建模板</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 14px"
      title="模板打包阶段天数、门禁规则、自定义字段、标签和字典项。新建项目时选择模板即自动套用;已有项目也可在列表中「套用」。同名的配置会被跳过,重复套用不会堆叠。"
    />

    <el-card v-loading="loading">
      <el-table :data="templates" border stripe empty-text="暂无模板">
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            {{ row.name }}
            <el-tag v-if="row.is_default" type="success" size="small" style="margin-left: 6px">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
        <el-table-column label="阶段天数" width="180">
          <template #default="{ row }">{{ daysText(row) }}</template>
        </el-table-column>
        <el-table-column label="包含内容" width="220">
          <template #default="{ row }">{{ summary(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openApply(row)">套用</el-button>
            <el-button v-if="isAdmin" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="isAdmin" link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模板' : '新建模板'" width="900px">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="基本信息" name="basic">
          <el-form label-width="90px">
            <el-form-item label="模板名称">
              <el-input v-model="form.name" maxlength="128" />
            </el-form-item>
            <el-form-item label="说明">
              <el-input v-model="form.description" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="设为默认">
              <el-switch v-model="form.is_default" />
              <span style="margin-left: 10px; color: #909399; font-size: 12px">新建项目未指定模板时自动套用默认模板</span>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="阶段天数" name="days">
          <el-form label-width="90px">
            <el-form-item v-for="s in STAGES" :key="s" :label="stageLabel(s)">
              <el-input-number v-model="form.stage_days[s]" :min="0" :max="365" />
              <span style="margin-left: 10px; color: #909399; font-size: 12px">填 0 表示不写入模板,项目沿用全局阶段配置</span>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="门禁规则" name="gates">
          <el-button size="small" @click="addGate">添加门禁</el-button>
          <el-table :data="form.gates" border size="small" style="margin-top: 8px" empty-text="未配置门禁">
            <el-table-column label="阶段" width="130">
              <template #default="{ row }">
                <el-select v-model="row.stage" size="small">
                  <el-option v-for="s in STAGES" :key="s" :label="stageLabel(s)" :value="s" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="110">
              <template #default="{ row }">
                <el-select v-model="row.kind" size="small">
                  <el-option v-for="k in KINDS" :key="k" :label="k" :value="k" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="规则" min-width="220">
              <template #default="{ row }">
                <el-select v-model="row.rule" size="small">
                  <el-option v-for="r in rules" :key="r.key" :label="r.label" :value="r.key" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="阈值" width="130">
              <template #default="{ row }"><el-input-number v-model="row.threshold" size="small" :min="0" /></template>
            </el-table-column>
            <el-table-column label="启用" width="70">
              <template #default="{ row }"><el-switch v-model="row.enabled" size="small" /></template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="form.gates.splice($index, 1)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="自定义字段" name="fields">
          <el-button size="small" @click="addField">添加字段</el-button>
          <el-table :data="form.custom_fields" border size="small" style="margin-top: 8px" empty-text="未配置字段">
            <el-table-column label="字段名" min-width="160">
              <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
            </el-table-column>
            <el-table-column label="类型" width="120">
              <template #default="{ row }">
                <el-select v-model="row.field_type" size="small">
                  <el-option v-for="t in FIELD_TYPES" :key="t.value" :label="t.label" :value="t.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="选项(逗号分隔)" min-width="200">
              <template #default="{ row }">
                <el-input v-model="row.options_text" size="small" :disabled="row.field_type !== 'select'" />
              </template>
            </el-table-column>
            <el-table-column label="必填" width="70">
              <template #default="{ row }"><el-switch v-model="row.required" size="small" /></template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="form.custom_fields.splice($index, 1)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="标签" name="tags">
          <el-button size="small" @click="addTag">添加标签</el-button>
          <el-table :data="form.tags" border size="small" style="margin-top: 8px" empty-text="未配置标签">
            <el-table-column label="标签名" min-width="180">
              <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
            </el-table-column>
            <el-table-column label="颜色" width="180">
              <template #default="{ row }"><el-color-picker v-model="row.color" size="small" /></template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="form.tags.splice($index, 1)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="字典项" name="dict">
          <el-button size="small" @click="addDictItem">添加字典项</el-button>
          <el-table :data="form.dict_items" border size="small" style="margin-top: 8px" empty-text="未配置字典项">
            <el-table-column label="字典类型" width="170">
              <template #default="{ row }">
                <el-select v-model="row.dict_key" size="small">
                  <el-option v-for="t in dictTypes" :key="t.key" :label="t.name" :value="t.key" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="选项名称" min-width="150">
              <template #default="{ row }"><el-input v-model="row.label" size="small" /></template>
            </el-table-column>
            <el-table-column label="色值" width="130">
              <template #default="{ row }">
                <el-select v-model="row.color" size="small">
                  <el-option v-for="c in COLORS" :key="c" :label="c" :value="c" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="排序" width="110">
              <template #default="{ row }"><el-input-number v-model="row.sort_order" size="small" :min="0" /></template>
            </el-table-column>
            <el-table-column label="紧急" width="70">
              <template #default="{ row }"><el-switch v-model="row.is_urgent" size="small" /></template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ $index }">
                <el-button link type="danger" size="small" @click="form.dict_items.splice($index, 1)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="collectVisible" title="从现有项目另存为模板" width="460px">
      <el-form label-width="70px">
        <el-form-item label="项目">
          <el-select v-model="savingFrom" filterable style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <div style="color: #909399; font-size: 12px">读取该项目的阶段天数、门禁、自定义字段、标签与字典项,填入新建模板表单,确认后再保存。</div>
      <template #footer>
        <el-button @click="collectVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="loadDraft">载入草稿</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="applyVisible" title="套用模板到项目" width="460px">
      <el-form label-width="70px">
        <el-form-item label="项目">
          <el-select v-model="applyForm.project_id" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <div style="color: #909399; font-size: 12px">同名的门禁、字段、标签和字典项会被跳过,只补齐缺少的配置。</div>
      <template #footer>
        <el-button @click="applyVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doApply">确定套用</el-button>
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
