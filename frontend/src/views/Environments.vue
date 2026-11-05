<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { envApi, projectApi, userApi } from '../api'

const STAGES = ['SIT', 'UAT', 'PRE']
const STATUSES = ['可用', '占用中', '维护中', '已停用']
const stageLabel = (s) => (s === 'PRE' ? '预发版' : s)
const statusTag = (s) => ({ 可用: 'success', 占用中: 'warning', 维护中: 'info', 已停用: 'danger' }[s] || 'info')

const loading = ref(false)
const saving = ref(false)
const projects = ref([])
const users = ref([])
const envs = ref([])
const filter = reactive({ project_id: null, stage: '', status: '' })

const dialogVisible = ref(false)
const editingId = ref(null)
const form = reactive({
  project_id: null, name: '', stage: 'SIT', status: '可用',
  url: '', version: '', owner_id: null, remark: '',
})

const runsVisible = ref(false)
const runsLoading = ref(false)
const runsTitle = ref('')
const runsList = ref([])

async function loadProjects() {
  projects.value = await projectApi.list()
  if (!filter.project_id && projects.value.length) {
    filter.project_id = projects.value[0].id
  }
}

async function load() {
  if (!filter.project_id) {
    envs.value = []
    return
  }
  loading.value = true
  try {
    const params = { project_id: filter.project_id }
    if (filter.stage) params.stage = filter.stage
    if (filter.status) params.status = filter.status
    envs.value = await envApi.list(params)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, {
    project_id: filter.project_id, name: '', stage: filter.stage || 'SIT', status: '可用',
    url: '', version: '', owner_id: null, remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, {
    project_id: row.project_id, name: row.name, stage: row.stage, status: row.status,
    url: row.url, version: row.version, owner_id: row.owner_id, remark: row.remark,
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.project_id) {
    ElMessage.error('请选择项目')
    return
  }
  if (!form.name.trim()) {
    ElMessage.error('请填写环境名称')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      const { project_id, ...rest } = form
      await envApi.update(editingId.value, rest)
    } else {
      await envApi.create({ ...form, name: form.name.trim() })
    }
    dialogVisible.value = false
    ElMessage.success('已保存')
    await load()
  } finally {
    saving.value = false
  }
}

async function disable(row) {
  await ElMessageBox.confirm(`确定停用环境「${row.name}」?停用后不能再在其上记录执行结果。`, '提示', { type: 'warning' })
  await envApi.update(row.id, { status: '已停用' })
  ElMessage.success('已停用')
  await load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除环境「${row.name}」?已被执行记录引用的环境不能删除。`, '提示', { type: 'warning' })
  await envApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

async function viewRuns(row) {
  runsTitle.value = `${row.name}(${stageLabel(row.stage)})`
  runsVisible.value = true
  runsLoading.value = true
  try {
    const res = await envApi.runs(row.id, { page_size: 50 })
    runsList.value = res.items
  } finally {
    runsLoading.value = false
  }
}

watch(() => [filter.project_id, filter.stage, filter.status], load)

onMounted(async () => {
  const [opts] = await Promise.all([userApi.options(), loadProjects()])
  users.value = opts
  await load()
})
</script>

<template>
  <div>
    <div class="page-header">
      <h2>测试环境</h2>
      <el-button type="primary" @click="openCreate" :disabled="!filter.project_id">新建环境</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 14px"
      title="环境按项目维护,执行结果可归属到具体环境;已停用环境不再接受新执行记录,被引用过的环境只能停用不能删除,以保留执行追溯链。"
    />

    <el-card v-loading="loading">
      <el-form :inline="true" style="margin-bottom: 8px">
        <el-form-item label="项目">
          <el-select v-model="filter.project_id" style="width: 220px">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="filter.stage" clearable placeholder="全部" style="width: 110px">
            <el-option v-for="s in STAGES" :key="s" :label="stageLabel(s)" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 120px">
            <el-option v-for="s in STATUSES" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-table :data="envs" border stripe empty-text="该项目暂未登记测试环境">
        <el-table-column prop="name" label="环境名称" min-width="150" />
        <el-table-column label="阶段" width="90">
          <template #default="{ row }"><el-tag size="small">{{ stageLabel(row.stage) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="url" label="访问地址" min-width="180" show-overflow-tooltip />
        <el-table-column prop="version" label="部署版本" width="130" show-overflow-tooltip />
        <el-table-column label="负责人" width="110">
          <template #default="{ row }">{{ row.owner_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="执行数" width="120">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewRuns(row)" :disabled="!row.run_count">{{ row.run_count }}</el-button>
            <span v-if="row.failed_count" style="margin-left: 6px; color: #f56c6c; font-size: 12px">失败/阻塞 {{ row.failed_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="disable(row)" :disabled="row.status === '已停用'">停用</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑测试环境' : '新建测试环境'" width="560px">
      <el-form label-width="90px">
        <el-form-item label="项目">
          <el-select v-model="form.project_id" style="width: 100%" :disabled="!!editingId">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境名称">
          <el-input v-model="form.name" placeholder="例如:SIT-核心交易、UAT-前置机1" />
        </el-form-item>
        <el-form-item label="主要阶段">
          <el-radio-group v-model="form.stage">
            <el-radio-button v-for="s in STAGES" :key="s" :value="s">{{ stageLabel(s) }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option v-for="s in STATUSES" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="访问地址">
          <el-input v-model="form.url" placeholder="例如:http://<your-server>:8080/core" />
        </el-form-item>
        <el-form-item label="部署版本">
          <el-input v-model="form.version" placeholder="例如:v1.0.3-20261105" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="form.owner_id" clearable placeholder="选择在职成员" style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="u.display_name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="数据库、中间件、注意事项等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runsVisible" :title="`执行记录 - ${runsTitle}`" width="820px">
      <el-table v-loading="runsLoading" :data="runsList" border stripe max-height="420" empty-text="该环境暂无执行记录">
        <el-table-column prop="run_id" label="ID" width="70" />
        <el-table-column prop="testcase_title" label="用例" min-width="200" show-overflow-tooltip />
        <el-table-column prop="plan_version" label="批次" width="120" />
        <el-table-column prop="stage" label="阶段" width="80" />
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === '通过' ? 'success' : row.status === '失败' ? 'danger' : 'warning'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
        <el-table-column label="执行时间" width="170">
          <template #default="{ row }">{{ row.executed_at ? new Date(row.executed_at).toLocaleString() : '-' }}</template>
        </el-table-column>
      </el-table>
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
