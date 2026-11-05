<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { gateApi, projectApi } from '../api'

const STAGES = ['SIT', 'UAT', 'PRE']
const KINDS = ['准入', '准出']
const stageLabel = (s) => (s === 'PRE' ? '预发版' : s)

const loading = ref(false)
const saving = ref(false)
const projects = ref([])
const rules = ref([])
const gates = ref([])
const filter = reactive({ project_id: null, stage: '', kind: '' })

const dialogVisible = ref(false)
const editingId = ref(null)
const form = reactive({ project_id: null, stage: 'SIT', kind: '准出', rule: 'pass_rate_min', threshold: 95, enabled: true })

const ruleMeta = computed(() => Object.fromEntries(rules.value.map((r) => [r.key, r])))
const currentRule = computed(() => ruleMeta.value[form.rule] || { unit: '', hint: '', op: '>=' })
const isPercent = computed(() => currentRule.value.unit === '%')

async function loadProjects() {
  projects.value = await projectApi.list()
  if (!filter.project_id && projects.value.length) {
    filter.project_id = projects.value[0].id
  }
}

async function load() {
  if (!filter.project_id) {
    gates.value = []
    return
  }
  loading.value = true
  try {
    const params = { project_id: filter.project_id }
    if (filter.stage) params.stage = filter.stage
    if (filter.kind) params.kind = filter.kind
    gates.value = await gateApi.list(params)
  } finally {
    loading.value = false
  }
}

function openCreate(kind = '准出') {
  editingId.value = null
  Object.assign(form, {
    project_id: filter.project_id,
    stage: filter.stage || 'SIT',
    kind,
    rule: kind === '准出' ? 'pass_rate_min' : 'review_approved_min',
    threshold: kind === '准出' ? 95 : 100,
    enabled: true,
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, {
    project_id: row.project_id,
    stage: row.stage,
    kind: row.kind,
    rule: row.rule,
    threshold: row.threshold,
    enabled: row.enabled,
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.project_id) {
    ElMessage.error('请选择项目')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await gateApi.update(editingId.value, {
        stage: form.stage, kind: form.kind, rule: form.rule,
        threshold: form.threshold, enabled: form.enabled,
      })
    } else {
      await gateApi.create({ ...form })
    }
    dialogVisible.value = false
    ElMessage.success('已保存')
    await load()
  } finally {
    saving.value = false
  }
}

async function toggle(row) {
  try {
    await gateApi.update(row.id, { enabled: row.enabled })
  } catch (e) {
    row.enabled = !row.enabled
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除门禁「${row.stage} ${row.kind} · ${row.rule_label}」?`, '提示', { type: 'warning' })
  await gateApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

watch(() => [filter.project_id, filter.stage, filter.kind], load)

onMounted(async () => {
  rules.value = await gateApi.rules()
  await loadProjects()
  await load()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h2>准入准出门禁</h2>
      <el-button type="primary" @click="openCreate('准出')" :disabled="!filter.project_id">新建准出规则</el-button>
      <el-button @click="openCreate('准入')" :disabled="!filter.project_id">新建准入规则</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 14px"
      title="推进阶段时校验「当前阶段准出 + 目标阶段准入」;标记计划完成时校验当前阶段准出。未达标会阻断操作,管理员可填写理由强制越权并留痕。未配置规则表示不限制。"
    />

    <el-card v-loading="loading">
      <el-form :inline="true" style="margin-bottom: 8px">
        <el-form-item label="项目">
          <el-select v-model="filter.project_id" style="width: 220px">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="filter.stage" clearable placeholder="全部" style="width: 120px">
            <el-option v-for="s in STAGES" :key="s" :label="stageLabel(s)" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="filter.kind" clearable placeholder="全部" style="width: 120px">
            <el-option v-for="k in KINDS" :key="k" :label="k" :value="k" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-table :data="gates" border stripe empty-text="该项目暂未配置门禁规则">
        <el-table-column prop="stage" label="阶段" width="90">
          <template #default="{ row }"><el-tag size="small">{{ stageLabel(row.stage) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="kind" label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.kind === '准出' ? 'warning' : 'success'">{{ row.kind }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rule_label" label="规则" min-width="200" />
        <el-table-column label="阈值" width="120">
          <template #default="{ row }">{{ row.op }} {{ row.threshold }}{{ row.unit }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }"><el-switch v-model="row.enabled" @change="toggle(row)" /></template>
        </el-table-column>
        <el-table-column label="说明" min-width="220">
          <template #default="{ row }"><span style="color: #909399; font-size: 12px">{{ row.hint }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑门禁规则' : '新建门禁规则'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="项目">
          <el-select v-model="form.project_id" style="width: 100%" :disabled="!!editingId">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="阶段">
          <el-radio-group v-model="form.stage">
            <el-radio-button v-for="s in STAGES" :key="s" :value="s">{{ stageLabel(s) }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.kind">
            <el-radio-button v-for="k in KINDS" :key="k" :value="k">{{ k }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="规则">
          <el-select v-model="form.rule" style="width: 100%">
            <el-option v-for="r in rules" :key="r.key" :label="r.label" :value="r.key">
              <span>{{ r.label }}</span>
              <span style="float: right; color: #909399; font-size: 12px">{{ r.hint }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="阈值">
          <el-input-number v-model="form.threshold" :min="0" :max="isPercent ? 100 : 99999" :step="isPercent ? 5 : 1" />
          <span style="margin-left: 10px; color: #909399">{{ currentRule.op === '>=' ? '不低于' : '不超过' }} {{ form.threshold }}{{ currentRule.unit }}</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
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
