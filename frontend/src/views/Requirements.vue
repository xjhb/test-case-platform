<template>
  <div>
    <div class="page-header">
      <h2>需求管理</h2>
      <el-radio-group v-model="viewMode" size="large">
        <el-radio-button label="list">需求列表</el-radio-button>
        <el-radio-button label="matrix">覆盖率矩阵</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 需求列表视图 -->
    <div v-if="viewMode === 'list'">
      <div class="filter">
        <el-select v-model="query.project_id" placeholder="项目" clearable style="width: 200px" @change="loadData">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-select v-model="query.priority" placeholder="优先级" clearable style="width: 120px" @change="loadData">
          <el-option label="高" value="高" />
          <el-option label="中" value="中" />
          <el-option label="低" value="低" />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 120px" @change="loadData">
          <el-option label="待处理" value="待处理" />
          <el-option label="进行中" value="进行中" />
          <el-option label="已完成" value="已完成" />
          <el-option label="已关闭" value="已关闭" />
        </el-select>
        <el-input v-model="query.keyword" placeholder="搜索需求编号/标题" clearable style="width: 200px" @keyup.enter="loadData" />
        <el-button type="primary" @click="loadData">查询</el-button>
        <el-button @click="resetQuery">重置</el-button>
        <el-button type="success" @click="openCreate" style="margin-left: auto">新建需求</el-button>
      </div>

      <el-table v-loading="loading" :data="list" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="req_no" label="需求编号" width="120" />
        <el-table-column prop="title" label="需求标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">
            <el-tag :type="priorityTagType(row.priority)" size="small">{{ row.priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联用例" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="showLinkedTestcases(row)">{{ row.testcase_count }}个</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="created_by_name" label="创建人" width="100" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="success" @click="openLinkTestcases(row)">关联用例</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        :total="total"
        :current-page="query.page"
        :page-size="query.page_size"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="pageChange"
        @size-change="sizeChange"
      />
    </div>

    <!-- 覆盖率矩阵视图 -->
    <div v-else>
      <div class="filter">
        <el-select v-model="matrixProjectId" placeholder="选择项目" style="width: 200px" @change="loadMatrix">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </div>

      <div v-if="matrixData" class="coverage-summary">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-card shadow="never">
              <div class="stat-num">{{ matrixData.total_requirements }}</div>
              <div class="stat-label">需求总数</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never">
              <div class="stat-num" style="color: #67c23a">{{ matrixData.covered_requirements }}</div>
              <div class="stat-label">已覆盖</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never">
              <div class="stat-num" style="color: #f56c6c">{{ matrixData.uncovered_requirements }}</div>
              <div class="stat-label">未覆盖</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never">
              <div class="stat-num" style="color: #409eff">{{ matrixData.coverage_rate }}%</div>
              <div class="stat-label">覆盖率</div>
            </el-card>
          </el-col>
        </el-row>
      </div>

      <el-table v-if="matrixData" :data="matrixData.matrix" border stripe>
        <el-table-column prop="req_no" label="需求编号" width="120" />
        <el-table-column prop="req_title" label="需求标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">
            <el-tag :type="priorityTagType(row.req_priority)" size="small">{{ row.req_priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.req_status)" size="small">{{ row.req_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="覆盖状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.covered ? 'success' : 'danger'" size="small">
              {{ row.covered ? '已覆盖' : '未覆盖' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联用例" width="120">
          <template #default="{ row }">
            <el-button v-if="row.covered" link type="primary" @click="showTestcaseIds(row.testcase_ids)">
              {{ row.testcase_count }}个
            </el-button>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑需求' : '新建需求'" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="项目" prop="project_id">
          <el-select v-model="form.project_id" placeholder="选择项目" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="需求编号" prop="req_no">
          <el-input v-model="form.req_no" placeholder="例如: REQ-001" />
        </el-form-item>
        <el-form-item label="需求标题" prop="title">
          <el-input v-model="form.title" placeholder="一句话描述需求" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width: 120px">
            <el-option label="高" value="高" />
            <el-option label="中" value="中" />
            <el-option label="低" value="低" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 120px">
            <el-option label="待处理" value="待处理" />
            <el-option label="进行中" value="进行中" />
            <el-option label="已完成" value="已完成" />
            <el-option label="已关闭" value="已关闭" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="详细描述需求" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 关联用例对话框 -->
    <el-dialog v-model="linkVisible" title="关联测试用例" width="700px">
      <div style="margin-bottom: 12px; color: #909399">
        当前需求: {{ currentReq?.req_no }} - {{ currentReq?.title }}
      </div>
      <el-table :data="availableTestcases" border stripe max-height="400">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="module" label="模块" width="120" />
        <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="优先级" width="80">
          <template #default="{ row }">
            <el-tag :type="priorityTagType(row.priority)" size="small">{{ row.priority }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="linkVisible = false">取消</el-button>
        <el-button type="primary" @click="submitLink">关联选中用例</el-button>
      </template>
    </el-dialog>

    <!-- 查看关联用例 -->
    <el-dialog v-model="testcasesVisible" title="关联的测试用例" width="700px">
      <el-table :data="linkedTestcases" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="module" label="模块" width="120" />
        <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="优先级" width="80">
          <template #default="{ row }">
            <el-tag :type="priorityTagType(row.priority)" size="small">{{ row.priority }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="testcasesVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectApi, requirementApi, testcaseApi } from '../api'

const viewMode = ref('list')
const projects = ref([])
const list = ref([])
const total = ref(0)
const loading = ref(false)
const matrixProjectId = ref('')
const matrixData = ref(null)

const query = reactive({
  project_id: '',
  priority: '',
  status: '',
  keyword: '',
  page: 1,
  page_size: 20,
})

const priorityTagType = (p) => ({ 高: 'danger', 中: 'warning', 低: 'info' }[p] || 'info')
const statusTagType = (s) => ({ 待处理: 'info', 进行中: 'warning', 已完成: 'success', 已关闭: '' }[s] || 'info')

async function loadProjects() {
  projects.value = await projectApi.list()
}

async function loadData() {
  if (!query.project_id) {
    list.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const params = {
      project_id: query.project_id,
      page: query.page,
      page_size: query.page_size,
    }
    if (query.priority) params.priority = query.priority
    if (query.status) params.status = query.status
    if (query.keyword) params.keyword = query.keyword
    const res = await requirementApi.list(params)
    list.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function loadMatrix() {
  if (!matrixProjectId.value) {
    matrixData.value = null
    return
  }
  try {
    matrixData.value = await requirementApi.coverageMatrix(matrixProjectId.value)
  } catch (e) {
    console.error(e)
  }
}

function resetQuery() {
  query.priority = ''
  query.status = ''
  query.keyword = ''
  loadData()
}

function pageChange(p) {
  query.page = p
  loadData()
}

function sizeChange(s) {
  query.page_size = s
  query.page = 1
  loadData()
}

// ---- 新建/编辑 ----
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()
const form = reactive({
  id: null,
  project_id: '',
  req_no: '',
  title: '',
  description: '',
  priority: '中',
  status: '待处理',
})
const rules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  req_no: [{ required: true, message: '请输入需求编号', trigger: 'blur' }],
  title: [{ required: true, message: '请输入需求标题', trigger: 'blur' }],
}

function resetForm() {
  form.id = null
  form.project_id = query.project_id || ''
  form.req_no = ''
  form.title = ''
  form.description = ''
  form.priority = '中'
  form.status = '待处理'
}

function openCreate() {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.id = row.id
  form.project_id = row.project_id
  form.req_no = row.req_no
  form.title = row.title
  form.description = row.description
  form.priority = row.priority
  form.status = row.status
  dialogVisible.value = true
}

async function submit() {
  await formRef.value.validate()
  const payload = {
    project_id: form.project_id,
    req_no: form.req_no,
    title: form.title,
    description: form.description,
    priority: form.priority,
    status: form.status,
  }
  if (isEdit.value) {
    await requirementApi.update(form.id, payload)
    ElMessage.success('修改成功')
  } else {
    await requirementApi.create(payload)
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false
  loadData()
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除需求「${row.title}」?`, '提示', { type: 'warning' })
  await requirementApi.remove(row.id)
  ElMessage.success('已删除')
  loadData()
}

// ---- 关联用例 ----
const linkVisible = ref(false)
const currentReq = ref(null)
const availableTestcases = ref([])

async function openLinkTestcases(row) {
  currentReq.value = row
  const res = await testcaseApi.list({ project_id: row.project_id, page_size: 200 })
  availableTestcases.value = res.items
  linkVisible.value = true
}

async function submitLink() {
  const selected = availableTestcases.value.filter((tc) => tc._checked)
  if (!selected.length) {
    ElMessage.warning('请至少选择一个用例')
    return
  }
  const ids = selected.map((tc) => tc.id)
  await requirementApi.linkTestcases(currentReq.value.id, ids)
  ElMessage.success(`已关联${ids.length}个用例`)
  linkVisible.value = false
  loadData()
}

// ---- 查看关联用例 ----
const testcasesVisible = ref(false)
const linkedTestcases = ref([])

async function showLinkedTestcases(row) {
  linkedTestcases.value = await requirementApi.getTestcases(row.id)
  testcasesVisible.value = true
}

function showTestcaseIds(ids) {
  ElMessageBox.alert(`关联的用例ID: ${ids.join(', ')}`, '关联用例', { type: 'info' })
}

onMounted(async () => {
  await loadProjects()
  if (projects.value.length) {
    query.project_id = projects.value[0].id
    matrixProjectId.value = projects.value[0].id
    loadData()
  }
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
}

.filter {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
  display: flex;
}

.coverage-summary {
  margin-bottom: 20px;
}

.coverage-summary .stat-num {
  font-size: 28px;
  font-weight: bold;
  text-align: center;
}

.coverage-summary .stat-label {
  text-align: center;
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
</style>
