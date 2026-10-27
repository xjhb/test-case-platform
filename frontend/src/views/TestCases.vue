<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectApi, testcaseApi, runApi, uploadApi, planApi, importApi, testcaseExportUrl, p2Api } from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.role === 'admin')
const allStagesMode = ref(false)

// ---- 倒计时 ----
const countdownData = ref(null)
const countdownText = ref('')
let countdownTimer = null

const countdownTitle = computed(() => {
  if (!countdownData.value) return ''
  const cd = countdownData.value
  return `阶段 ${stageLabel(cd.stage)} | 时间范围:${cd.start || '?'} ~ ${cd.end || '?'}`
})
const countdownType = computed(() => {
  if (!countdownData.value) return 'info'
  if (countdownData.value.expired) return 'error'
  if (countdownData.value.remaining_seconds !== null && countdownData.value.remaining_seconds < 86400) return 'warning'
  return 'success'
})

function formatCountdown(seconds) {
  if (seconds <= 0) return '已超时'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (d > 0) return `${d}天 ${h}时 ${m}分 ${s}秒`
  if (h > 0) return `${h}时 ${m}分 ${s}秒`
  return `${m}分 ${s}秒`
}

async function loadCountdown() {
  if (!query.plan_id) {
    countdownData.value = null
    return
  }
  try {
    // 倒计时跟随所选阶段(SIT/UAT/PRE),而非批次当前阶段
    countdownData.value = await planApi.countdown(query.plan_id, activeStage.value)
    updateCountdownText()
  } catch (e) {
    countdownData.value = null
  }
}

function updateCountdownText() {
  if (countdownData.value && countdownData.value.remaining_seconds !== null) {
    countdownText.value = formatCountdown(countdownData.value.remaining_seconds)
    if (countdownData.value.remaining_seconds > 0) {
      countdownData.value.remaining_seconds--
    }
  }
}

function startCountdownTimer() {
  if (countdownTimer) clearInterval(countdownTimer)
  countdownTimer = setInterval(updateCountdownText, 1000)
}

const STATUS_OPTIONS = [
  { label: '未执行', value: '未执行' },
  { label: '通过', value: '通过' },
  { label: '失败', value: '失败' },
  { label: '阻塞', value: '阻塞' },
]
const PRIORITY_OPTIONS = [
  { label: 'P0', value: 'P0' },
  { label: 'P1', value: 'P1' },
  { label: 'P2', value: 'P2' },
  { label: 'P3', value: 'P3' },
]
const REVIEW_STATUS_OPTIONS = [
  { label: '草稿', value: '草稿' },
  { label: '评审中', value: '评审中' },
  { label: '已批准', value: '已批准' },
  { label: '已驳回', value: '已驳回' },
]

const statusTagType = (s) => ({ 未执行: 'info', 通过: 'success', 失败: 'danger', 阻塞: 'warning' }[s] || 'info')
const priorityTagType = (p) => ({ P0: 'danger', P1: 'warning', P2: 'primary', P3: 'info' }[p] || 'info')
const reviewStatusTagType = (s) => ({ 草稿: 'info', 评审中: 'warning', 已批准: 'success', 已驳回: 'danger' }[s] || 'info')

const projects = ref([])
const plans = ref([])
const list = ref([])
const total = ref(0)
const loading = ref(false)
const stats = ref({ total: 0, by_status: {}, by_priority: {} })

const query = reactive({
  project_id: '',
  plan_id: '',
  stage: '',
  status: '',
  priority: '',
  review_status: '',
  keyword: '',
  page: 1,
  page_size: 20,
})

// 当前选中计划对象(用于显示计划当前阶段、状态)
const currentPlan = computed(() => plans.value.find((p) => p.id === query.plan_id) || null)
const currentStage = computed(() => currentPlan.value?.current_stage || '')

// 执行/筛选使用的阶段:由用户显式选择,不再跟随计划当前阶段。
// 三个阶段可独立执行(SIT/UAT/PRE 无先后限制)。
const STAGE_OPTIONS = [
  { value: 'SIT', label: 'SIT' },
  { value: 'UAT', label: 'UAT' },
  { value: 'PRE', label: '预发版(PRE)' },
]
// 查询阶段:未选时默认 SIT
const activeStage = computed(() => query.stage || 'SIT')

// ---- 加载数据 ----
async function loadProjects() {
  projects.value = await projectApi.list()
}

async function loadPlans() {
  if (!query.project_id) {
    plans.value = []
    query.plan_id = ''
    return
  }
  plans.value = await planApi.list({ project_id: query.project_id })
  if (plans.value.length) {
    query.plan_id = plans.value[0].id
  } else {
    query.plan_id = ''
  }
  // 阶段由用户独立选择,不随项目/计划重置;未选时默认 SIT
  if (!query.stage) query.stage = 'SIT'
}

function onProjectChange() {
  query.plan_id = ''
  selectedFolderId.value = null
  loadPlans().then(() => search())
  loadFolders()
  loadTags()
  loadCustomFields()
}

function onPlanChange() {
  // 切换计划不改变已选阶段
  if (!query.stage) query.stage = 'SIT'
  search()
  loadCountdown()
}

// 手动切换阶段:重新筛选 + 刷新倒计时
function onStageChange() {
  search()
  loadCountdown()
}

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, page_size: query.page_size }
    if (query.project_id) params.project_id = query.project_id
    if (query.plan_id) params.plan_id = query.plan_id
    // 全阶段总览模式(超管):不传 stage,传 all_stages=true
    if (allStagesMode.value && isAdmin.value) {
      params.all_stages = true
    } else {
      // 始终按显式选择的阶段筛选(默认 SIT)
      params.stage = activeStage.value
    }
    if (query.status) params.status = query.status
    if (query.priority) params.priority = query.priority
    if (query.review_status) params.review_status = query.review_status
    if (query.keyword) params.keyword = query.keyword
    if (selectedFolderId.value) params.folder_id = selectedFolderId.value
    const res = await testcaseApi.list(params)
    list.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  const params = {}
  if (query.project_id) params.project_id = query.project_id
  if (query.plan_id) params.plan_id = query.plan_id
  params.stage = activeStage.value
  stats.value = await testcaseApi.stats(params)
}

function search() {
  query.page = 1
  load()
  loadStats()
}

function resetQuery() {
  query.status = ''
  query.priority = ''
  query.review_status = ''
  query.keyword = ''
  search()
}

function pageChange(p) {
  query.page = p
  load()
}
function sizeChange(s) {
  query.page_size = s
  query.page = 1
  load()
}

// ---- 新建/编辑 ----
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()
const form = reactive({
  id: null,
  project_id: '',
  module: '',
  title: '',
  precondition: '',
  steps: '',
  expected: '',
  priority: 'P1',
})
const rules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  title: [{ required: true, message: '请输入用例标题', trigger: 'blur' }],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }],
}

function resetForm() {
  form.id = null
  form.project_id = query.project_id || ''
  form.module = ''
  form.title = ''
  form.precondition = ''
  form.steps = ''
  form.expected = ''
  form.priority = 'P1'
}

function openCreate() {
  if (!projects.value.length) {
    ElMessage.warning('请先到「项目管理」创建一个项目')
    return
  }
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.id = row.id
  form.project_id = row.project_id
  form.module = row.module
  form.title = row.title
  form.precondition = row.precondition
  form.steps = row.steps
  form.expected = row.expected
  form.priority = row.priority
  dialogVisible.value = true
}

function openVersions(row) {
  router.push(`/testcases/${row.id}/versions`)
}

// ---- 评审操作 ----
const rejectVisible = ref(false)
const rejectForm = reactive({ testcase_id: null, comment: '' })
const rejectTitle = ref('')

async function submitReview(row) {
  await ElMessageBox.confirm(`确定将用例「${row.title}」提交评审?`, '提示', { type: 'info' })
  await testcaseApi.submitReview(row.id)
  ElMessage.success('已提交评审')
  load()
}

function openApprove(row) {
  ElMessageBox.confirm(`确定批准用例「${row.title}」?`, '批准确认', { type: 'success' })
    .then(async () => {
      await testcaseApi.approve(row.id, '')
      ElMessage.success('已批准')
      load()
    })
    .catch(() => {})
}

function openReject(row) {
  rejectForm.testcase_id = row.id
  rejectForm.comment = ''
  rejectTitle.value = `驳回用例 - ${row.title}`
  rejectVisible.value = true
}

async function submitReject() {
  if (!rejectForm.comment.trim()) {
    ElMessage.warning('请填写驳回意见')
    return
  }
  await testcaseApi.reject(rejectForm.testcase_id, rejectForm.comment)
  ElMessage.success('已驳回')
  rejectVisible.value = false
  load()
}

async function submit() {
  await formRef.value.validate()
  const payload = {
    project_id: form.project_id,
    module: form.module,
    title: form.title,
    precondition: form.precondition,
    steps: form.steps,
    expected: form.expected,
    priority: form.priority,
  }
  if (isEdit.value) {
    await testcaseApi.update(form.id, payload)
    ElMessage.success('修改成功')
  } else {
    await testcaseApi.create(payload)
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false
  load()
  loadStats()
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除用例「${row.title}」?`, '提示', { type: 'warning' })
  await testcaseApi.remove(row.id)
  ElMessage.success('已删除')
  load()
  loadStats()
}

// ---- 导入 ----
const importVisible = ref(false)
const importProjectId = ref('')
const importLoading = ref(false)

function openImport() {
  if (!query.project_id) {
    ElMessage.warning('请先选择项目')
    return
  }
  importProjectId.value = query.project_id
  importVisible.value = true
}

async function exportTestcases() {
  if (!query.project_id) {
    ElMessage.warning('请先选择项目')
    return
  }
  const token = localStorage.getItem('token') || ''
  const resp = await fetch(testcaseExportUrl(query.project_id), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok) {
    ElMessage.error('导出失败')
    return
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '测试用例.xlsx'
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('用例已导出')
}

async function downloadTemplate() {
  const token = localStorage.getItem('token') || ''
  const resp = await fetch('/api/imports/template', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok) {
    ElMessage.error('模板下载失败')
    return
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'testcase_template.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}

async function handleImportUpload(opt) {
  importLoading.value = true
  try {
    const file = opt.file
    const res = await importApi.importFile(importProjectId.value, file)
    ElMessage.success(`导入完成:成功 ${res.created} 条,失败 ${res.failed} 条`)
    if (res.errors?.length) {
      ElMessageBox.alert(res.errors.slice(0, 20).join('\n'), '部分行跳过', { type: 'warning' })
    }
    importVisible.value = false
    load()
    loadStats()
  } catch (e) {
    // 拦截器已报错
  } finally {
    importLoading.value = false
  }
}

// ---- 执行 ----
const execVisible = ref(false)
const execFormRef = ref()
const execForm = reactive({ testcase_id: null, status: '通过', remark: '', screenshot: '' })
const execRules = {
  status: [{ required: true, message: '请选择执行结果', trigger: 'change' }],
}
const uploadImageUrl = uploadApi.imageUrl
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('token') || ''}` }))
const execFileList = ref([])

function openExec(row) {
  if (!query.plan_id) {
    ElMessage.warning('请先选择项目批次(测试计划),执行结果会记录到所选阶段')
    return
  }
  execForm.testcase_id = row.id
  execForm.status = '通过'
  execForm.remark = ''
  execForm.screenshot = ''
  execFileList.value = []
  execVisible.value = true
}

function beforeUpload(file) {
  const allowed = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp']
  if (!allowed.includes(file.type)) {
    ElMessage.error('仅支持 png/jpg/jpeg/gif/webp 格式图片')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 10MB')
    return false
  }
  return true
}

function handleUploadSuccess(res) {
  execForm.screenshot = res.url
  ElMessage.success('图片上传成功')
}

function handleRemove() {
  execForm.screenshot = ''
}

async function submitExec() {
  await execFormRef.value.validate()
  if (execForm.status === '通过' && !execForm.screenshot) {
    ElMessage.error('未上传图片,选择"通过"时必须上传成功截图')
    return
  }
  await runApi.create({
    plan_id: query.plan_id,
    testcase_id: execForm.testcase_id,
    status: execForm.status,
    remark: execForm.remark,
    screenshot: execForm.screenshot,
    // 显式指定执行阶段,不再由后端取计划当前阶段
    stage: activeStage.value,
  })
  ElMessage.success(`已记录执行结果(阶段:${stageLabel(activeStage.value)})`)
  execVisible.value = false
  load()
  loadStats()
}

// ---- 执行历史 ----
const historyVisible = ref(false)
const historyList = ref([])
const historyLoading = ref(false)
const historyTitle = ref('')

async function openHistory(row) {
  if (!query.plan_id) {
    ElMessage.warning('请先选择一个测试计划')
    return
  }
  historyTitle.value = `执行历史 - ${row.title}`
  historyVisible.value = true
  historyLoading.value = true
  try {
    historyList.value = await runApi.list(row.id, query.plan_id)
  } finally {
    historyLoading.value = false
  }
}

const stageTagType = (s) => ({ SIT: 'primary', UAT: 'warning', PRE: 'danger' }[s] || 'info')
const stageLabel = (s) => ({ SIT: 'SIT', UAT: 'UAT', PRE: '预发版' }[s] || s)

// ---- 文件夹目录树 ----
const folderTree = ref([])
const selectedFolderId = ref(null)
const folderDialogVisible = ref(false)
const folderForm = reactive({ name: '', parent_id: null })

async function loadFolders() {
  if (!query.project_id) {
    folderTree.value = []
    return
  }
  try {
    folderTree.value = await p2Api.listFolders(query.project_id)
  } catch (e) {
    folderTree.value = []
  }
}

function onFolderSelect(node) {
  selectedFolderId.value = node.id
  query.page = 1
  load()
}

function clearFolderSelect() {
  selectedFolderId.value = null
  query.page = 1
  load()
}

function openCreateFolder(parentId = null) {
  folderForm.name = ''
  folderForm.parent_id = parentId
  folderDialogVisible.value = true
}

async function submitFolder() {
  if (!folderForm.name.trim()) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  await p2Api.createFolder({ project_id: query.project_id, parent_id: folderForm.parent_id, name: folderForm.name })
  ElMessage.success('文件夹已创建')
  folderDialogVisible.value = false
  loadFolders()
}

async function deleteFolder(node) {
  await ElMessageBox.confirm(`确定删除文件夹「${node.name}」? 其下用例会移至根目录。`, '提示', { type: 'warning' })
  await p2Api.deleteFolder(node.id)
  ElMessage.success('已删除')
  if (selectedFolderId.value === node.id) selectedFolderId.value = null
  loadFolders()
  load()
}

// ---- 标签 ----
const tagList = ref([])
const tagDialogVisible = ref(false)
const tagForm = reactive({ name: '', color: '#409EFF' })
const assignTagVisible = ref(false)
const assignTagTcid = ref(null)
const assignTagIds = ref([])
const testcaseTagsMap = ref({})

async function loadTags() {
  if (!query.project_id) {
    tagList.value = []
    return
  }
  try {
    tagList.value = await p2Api.listTags(query.project_id)
  } catch (e) {
    tagList.value = []
  }
}

function openCreateTag() {
  tagForm.name = ''
  tagForm.color = '#409EFF'
  tagDialogVisible.value = true
}

async function submitTag() {
  if (!tagForm.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  await p2Api.createTag({ project_id: query.project_id, name: tagForm.name, color: tagForm.color })
  ElMessage.success('标签已创建')
  tagDialogVisible.value = false
  loadTags()
}

async function deleteTag(tag) {
  await ElMessageBox.confirm(`确定删除标签「${tag.name}」?`, '提示', { type: 'warning' })
  await p2Api.deleteTag(tag.id)
  ElMessage.success('已删除')
  loadTags()
}

async function openAssignTags(row) {
  assignTagTcid.value = row.id
  try {
    const tags = await p2Api.getTestcaseTags(row.id)
    assignTagIds.value = tags.map(t => t.id)
  } catch (e) {
    assignTagIds.value = []
  }
  assignTagVisible.value = true
}

async function submitAssignTags() {
  await p2Api.assignTags(assignTagTcid.value, assignTagIds.value)
  ElMessage.success('标签已更新')
  assignTagVisible.value = false
}

// ---- 自定义字段 ----
const customFields = ref([])
const cfDialogVisible = ref(false)
const cfForm = reactive({ name: '', field_type: 'text', options: '' })
const editCfVisible = ref(false)
const editCfTcid = ref(null)
const editCfValues = ref([])

async function loadCustomFields() {
  if (!query.project_id) {
    customFields.value = []
    return
  }
  try {
    customFields.value = await p2Api.listCustomFields(query.project_id)
  } catch (e) {
    customFields.value = []
  }
}

function openCreateCf() {
  cfForm.name = ''
  cfForm.field_type = 'text'
  cfForm.options = ''
  cfDialogVisible.value = true
}

async function submitCf() {
  if (!cfForm.name.trim()) {
    ElMessage.warning('请输入字段名称')
    return
  }
  await p2Api.createCustomField({
    project_id: query.project_id, name: cfForm.name,
    field_type: cfForm.field_type, options: cfForm.options,
  })
  ElMessage.success('自定义字段已创建')
  cfDialogVisible.value = false
  loadCustomFields()
}

async function deleteCf(field) {
  await ElMessageBox.confirm(`确定删除字段「${field.name}」? 相关值也会被清除。`, '提示', { type: 'warning' })
  await p2Api.deleteCustomField(field.id)
  ElMessage.success('已删除')
  loadCustomFields()
}

async function openEditCf(row) {
  editCfTcid.value = row.id
  try {
    editCfValues.value = await p2Api.getTestcaseCustomFields(row.id)
  } catch (e) {
    editCfValues.value = []
  }
  editCfVisible.value = true
}

async function submitEditCf() {
  const values = editCfValues.value.map(v => ({ field_id: v.field_id, value: v.value || '' }))
  await p2Api.setTestcaseCustomFields(editCfTcid.value, values)
  ElMessage.success('自定义字段值已保存')
  editCfVisible.value = false
}

function getCfValue(fieldId) {
  const item = editCfValues.value.find(v => v.field_id === fieldId)
  return item ? item.value : ''
}

function setCfValue(fieldId, val) {
  const item = editCfValues.value.find(v => v.field_id === fieldId)
  if (item) {
    item.value = val
  } else {
    editCfValues.value.push({ field_id: fieldId, value: val })
  }
}

function getCfOptions(field) {
  if (!field.options) return []
  return field.options.split(',').map(s => s.trim()).filter(Boolean)
}

onMounted(async () => {
  await loadProjects()
  // 从URL query接收项目+批次+阶段自动筛选
  if (route.query.project_id) {
    query.project_id = Number(route.query.project_id)
  } else if (projects.value.length) {
    query.project_id = projects.value[0].id
  }
  await loadPlans()
  if (route.query.plan_id) {
    query.plan_id = Number(route.query.plan_id)
  }
  // URL 可指定阶段;默认 SIT(用户之后可自由切换)
  if (route.query.stage && ['SIT', 'UAT', 'PRE'].includes(String(route.query.stage).toUpperCase())) {
    query.stage = String(route.query.stage).toUpperCase()
  } else if (!query.stage) {
    query.stage = 'SIT'
  }
  search()
  loadCountdown()
  startCountdownTimer()
  loadFolders()
  loadTags()
  loadCustomFields()
})

onBeforeUnmount(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})
</script>

<template>
  <div class="testcase-page">
    <!-- 左侧文件夹目录树 -->
    <div class="folder-sidebar" v-if="query.project_id">
      <div class="folder-header">
        <span class="folder-title">用例目录</span>
        <el-button link type="primary" size="small" @click="openCreateFolder(null)">
          <el-icon><Plus /></el-icon>
        </el-button>
      </div>
      <div class="folder-tree">
        <div
          class="folder-node folder-root"
          :class="{ active: !selectedFolderId }"
          @click="clearFolderSelect"
        >
          <el-icon><FolderOpened /></el-icon>
          <span>全部用例</span>
        </div>
        <el-tree
          v-if="folderTree.length"
          :data="folderTree"
          :props="{ label: 'name', children: 'children' }"
          node-key="id"
          highlight-current
          default-expand-all
          @node-click="onFolderSelect"
        >
          <template #default="{ node, data }">
            <div class="folder-tree-node">
              <el-icon><Folder /></el-icon>
              <span class="folder-node-label">{{ data.name }}</span>
              <el-badge :value="data.testcase_count" :hidden="!data.testcase_count" type="info" class="folder-badge" />
              <span class="folder-node-actions">
                <el-button link size="small" @click.stop="openCreateFolder(data.id)"><el-icon><Plus /></el-icon></el-button>
                <el-button link size="small" type="danger" @click.stop="deleteFolder(data)"><el-icon><Delete /></el-icon></el-button>
              </span>
            </div>
          </template>
        </el-tree>
        <div v-else class="folder-empty">暂无文件夹</div>
      </div>

      <!-- 标签管理 -->
      <div class="sidebar-section">
        <div class="folder-header">
          <span class="folder-title">标签</span>
          <el-button link type="primary" size="small" @click="openCreateTag">
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>
        <div class="tag-list" v-if="tagList.length">
          <el-tag v-for="tag in tagList" :key="tag.id" :color="tag.color" effect="dark" size="small" class="tag-item" closable @close="deleteTag(tag)">
            {{ tag.name }}
          </el-tag>
        </div>
        <div v-else class="folder-empty">暂无标签</div>
      </div>

      <!-- 自定义字段管理 -->
      <div class="sidebar-section">
        <div class="folder-header">
          <span class="folder-title">自定义字段</span>
          <el-button link type="primary" size="small" @click="openCreateCf">
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>
        <div class="cf-list" v-if="customFields.length">
          <div v-for="cf in customFields" :key="cf.id" class="cf-item">
            <span>{{ cf.name }}</span>
            <el-tag size="small" type="info">{{ cf.field_type }}</el-tag>
            <el-button link size="small" type="danger" @click="deleteCf(cf)"><el-icon><Delete /></el-icon></el-button>
          </div>
        </div>
        <div v-else class="folder-empty">暂无自定义字段</div>
      </div>
    </div>

    <!-- 右侧主内容 -->
    <div class="main-content">
    <!-- 统计卡片 -->
    <div class="stats">
      <el-card class="stat-card" shadow="never">
        <div class="stat-num">{{ stats.total }}</div>
        <div class="stat-label">用例总数</div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-num" style="color: #67c23a">{{ stats.by_status['通过'] || 0 }}</div>
        <div class="stat-label">通过</div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-num" style="color: #f56c6c">{{ stats.by_status['失败'] || 0 }}</div>
        <div class="stat-label">失败</div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-num" style="color: #e6a23c">{{ stats.by_status['阻塞'] || 0 }}</div>
        <div class="stat-label">阻塞</div>
      </el-card>
      <el-card class="stat-card" shadow="never">
        <div class="stat-num" style="color: #909399">{{ stats.by_status['未执行'] || 0 }}</div>
        <div class="stat-label">未执行</div>
      </el-card>
    </div>

    <!-- 筛选 -->
    <div class="filter">
      <el-select v-model="query.project_id" placeholder="项目" clearable style="width: 160px" @change="onProjectChange">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        <el-option v-if="!projects.length" disabled value="" label="暂无项目" />
      </el-select>
      <el-select v-model="query.plan_id" placeholder="迭代批次" clearable style="width: 180px" @change="onPlanChange">
        <el-option v-for="p in plans" :key="p.id" :label="p.version + ' (' + stageLabel(p.current_stage) + ')'" :value="p.id" />
        <el-option v-if="query.project_id && !plans.length" disabled value="" label="该项目暂无迭代批次" />
      </el-select>
      <!-- 阶段筛选:三阶段可独立选择,无先后限制 -->
      <el-select
        v-model="query.stage"
        placeholder="阶段"
        style="width: 140px"
        :disabled="allStagesMode"
        @change="onStageChange"
      >
        <el-option v-for="s in STAGE_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-switch
        v-if="isAdmin && query.plan_id"
        v-model="allStagesMode"
        active-text="全阶段总览"
        inactive-text="单阶段"
        style="margin-right: 4px"
        @change="search"
      />
      <el-tag v-if="currentStage && !allStagesMode" type="info" effect="plain" style="margin-right: 4px">
        批次当前阶段:{{ stageLabel(currentStage) }}
      </el-tag>
      <el-tag v-if="allStagesMode" type="danger" effect="plain" style="margin-right: 4px">
        全阶段总览(SIT/UAT/预发版)
      </el-tag>
      <el-select v-model="query.status" placeholder="状态" clearable style="width: 120px">
        <el-option v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-select v-model="query.priority" placeholder="优先级" clearable style="width: 110px">
        <el-option v-for="p in PRIORITY_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
      </el-select>
      <el-select v-model="query.review_status" placeholder="评审状态" clearable style="width: 130px">
        <el-option v-for="s in REVIEW_STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-input v-model="query.keyword" placeholder="搜索标题/模块" clearable style="width: 200px" @keyup.enter="search" />
      <el-button type="primary" @click="search">查询</el-button>
      <el-button @click="resetQuery">重置</el-button>
      <el-button type="success" @click="openImport" style="margin-left: auto">
        <el-icon><Upload /></el-icon>导入用例
      </el-button>
      <el-button type="warning" @click="exportTestcases" :disabled="!query.project_id">
        <el-icon><Download /></el-icon>导出用例
      </el-button>
    </div>

    <el-alert
      v-if="!query.plan_id"
      title="未选择测试计划:仅可查看/管理用例,无法执行。请先到「测试计划」创建计划,或在此选择计划。"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    />

    <!-- 倒计时横幅 -->
    <el-alert
      v-if="countdownData && query.plan_id"
      :title="countdownTitle"
      :type="countdownType"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      <span v-if="countdownData.expired" style="font-weight: bold; color: #f56c6c">
        阶段{{ stageLabel(countdownData.stage) }}已超时!请尽快完成或推进。
      </span>
      <span v-else style="font-weight: bold">
        剩余时间:{{ countdownText }}
      </span>
    </el-alert>

    <!-- 表格 -->
    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="module" label="模块" width="120" show-overflow-tooltip />
      <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="优先级" width="90">
        <template #default="{ row }">
          <el-tag :type="priorityTagType(row.priority)" size="small">{{ row.priority }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="评审状态" width="110">
        <template #default="{ row }">
          <el-tag :type="reviewStatusTagType(row.review_status)" size="small">{{ row.review_status }}</el-tag>
        </template>
      </el-table-column>
      <!-- 总览模式:三阶段状态 -->
      <template v-if="allStagesMode">
        <el-table-column label="SIT" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.sit_status)" size="small">{{ row.sit_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="UAT" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.uat_status)" size="small">{{ row.uat_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="PRE" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.pre_status)" size="small">{{ row.pre_status }}</el-tag>
          </template>
        </el-table-column>
      </template>
      <!-- 普通模式:单阶段状态 -->
      <el-table-column v-else label="当前阶段状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.latest_status)" size="small">{{ row.latest_status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="截图" width="80">
        <template #default="{ row }">
          <el-image
            v-if="row.latest_screenshot"
            :src="row.latest_screenshot"
            :preview-src-list="[row.latest_screenshot]"
            fit="cover"
            style="width: 44px; height: 44px; border-radius: 4px"
            preview-teleported
          />
          <span v-else style="color: #c0c4cc">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="170">
        <template #default="{ row }">
          {{ new Date(row.updated_at).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="360" fixed="right">
        <template #default="{ row }">
          <el-button link type="success" @click="openExec(row)">执行</el-button>
          <el-button link type="primary" @click="openHistory(row)">历史</el-button>
          <el-button link type="info" @click="openVersions(row)">版本</el-button>
          <el-button
            v-if="row.review_status === '草稿' || row.review_status === '已驳回'"
            link
            type="warning"
            @click="submitReview(row)"
          >提交评审</el-button>
          <el-button
            v-if="row.review_status === '评审中'"
            link
            type="success"
            @click="openApprove(row)"
          >批准</el-button>
          <el-button
            v-if="row.review_status === '评审中'"
            link
            type="danger"
            @click="openReject(row)"
          >驳回</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
          <el-button link type="warning" @click="openAssignTags(row)">标签</el-button>
          <el-button v-if="customFields.length" link type="info" @click="openEditCf(row)">字段</el-button>
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

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑用例' : '新建用例'" width="640px" top="6vh">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="项目" prop="project_id">
          <el-select v-model="form.project_id" placeholder="选择项目" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="模块" prop="module">
          <el-input v-model="form.module" placeholder="例如:登录/下单/退款" />
        </el-form-item>
        <el-form-item label="用例标题" prop="title">
          <el-input v-model="form.title" placeholder="一句话描述测试点" />
        </el-form-item>
        <el-form-item label="优先级" prop="priority">
          <el-select v-model="form.priority" style="width: 120px">
            <el-option v-for="p in PRIORITY_OPTIONS" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="前置条件">
          <el-input v-model="form.precondition" type="textarea" :rows="2" placeholder="例如:已登录普通用户账号" />
        </el-form-item>
        <el-form-item label="测试步骤">
          <el-input v-model="form.steps" type="textarea" :rows="4" placeholder="1. ...&#10;2. ...&#10;3. ..." />
        </el-form-item>
        <el-form-item label="预期结果">
          <el-input v-model="form.expected" type="textarea" :rows="3" placeholder="期望发生的现象" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 执行对话框 -->
    <el-dialog v-model="execVisible" title="记录执行结果" width="520px">
      <el-alert
        :title="`本次执行将记录到阶段:${stageLabel(activeStage)}`"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />
      <el-form ref="execFormRef" :model="execForm" :rules="execRules" label-width="90px">
        <el-form-item label="执行阶段">
          <el-select v-model="query.stage" style="width: 160px" @change="onStageChange">
            <el-option v-for="s in STAGE_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="执行结果" prop="status">
          <el-radio-group v-model="execForm.status">
            <el-radio value="通过">通过</el-radio>
            <el-radio value="失败">失败</el-radio>
            <el-radio value="阻塞">阻塞</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="execForm.status === '通过'" label="成功截图" required>
          <el-upload
            :action="uploadImageUrl"
            :headers="uploadHeaders"
            :file-list="execFileList"
            :before-upload="beforeUpload"
            :on-success="handleUploadSuccess"
            :on-remove="handleRemove"
            :limit="1"
            list-type="picture"
            accept="image/png,image/jpeg,image/gif,image/webp"
          >
            <el-button type="primary">
              <el-icon><Upload /></el-icon>选择图片
            </el-button>
            <template #tip>
              <div class="el-upload__tip">选择"通过"时必须上传成功截图(png/jpg/gif/webp,≤10MB)</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="备注/缺陷">
          <el-input v-model="execForm.remark" type="textarea" :rows="3" placeholder="失败/阻塞时填写原因或缺陷链接" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="execVisible = false">取消</el-button>
        <el-button type="primary" @click="submitExec">提交</el-button>
      </template>
    </el-dialog>

    <!-- 执行历史 -->
    <el-dialog v-model="historyVisible" :title="historyTitle" width="720px">
      <el-table v-loading="historyLoading" :data="historyList" border size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="阶段" width="90">
          <template #default="{ row }">
            <el-tag :type="stageTagType(row.stage)" size="small">{{ stageLabel(row.stage) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="截图" width="80">
          <template #default="{ row }">
            <el-image
              v-if="row.screenshot"
              :src="row.screenshot"
              :preview-src-list="[row.screenshot]"
              fit="cover"
              style="width: 44px; height: 44px; border-radius: 4px"
              preview-teleported
            />
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
        <el-table-column prop="executed_at" label="执行时间" width="170">
          <template #default="{ row }">
            {{ new Date(row.executed_at).toLocaleString() }}
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!historyLoading && !historyList.length" description="暂无执行记录" />
    </el-dialog>

    <!-- 导入用例 -->
    <el-dialog v-model="importVisible" title="导入测试用例" width="480px">
      <div style="margin-bottom: 12px">
        <el-button type="primary" link @click="downloadTemplate">
          <el-icon><Download /></el-icon>下载导入模板(.xlsx)
        </el-button>
        <span style="color: #909399; font-size: 12px; margin-left: 8px">先下载模板,按格式填写后上传</span>
      </div>
      <el-upload
        drag
        :auto-upload="true"
        :show-file-list="false"
        accept=".xlsx,.csv"
        :http-request="handleImportUpload"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">将文件拖到此处,或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 .xlsx / .csv,列:模块、用例标题、前置条件、测试步骤、预期结果、优先级</div>
        </template>
      </el-upload>
      <div v-loading="importLoading" style="text-align: center; color: #909399; margin-top: 8px">
        {{ importLoading ? '导入中...' : '' }}
      </div>
    </el-dialog>

    <!-- 驳回对话框 -->
    <el-dialog v-model="rejectVisible" :title="rejectTitle" width="500px">
      <el-form label-width="80px">
        <el-form-item label="驳回意见" required>
          <el-input
            v-model="rejectForm.comment"
            type="textarea"
            :rows="4"
            placeholder="请填写驳回原因,以便用例编写人修改"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rejectVisible = false">取消</el-button>
        <el-button type="danger" @click="submitReject">确认驳回</el-button>
      </template>
    </el-dialog>

    <!-- 新建文件夹对话框 -->
    <el-dialog v-model="folderDialogVisible" title="新建文件夹" width="420px">
      <el-form label-width="90px">
        <el-form-item label="文件夹名称" required>
          <el-input v-model="folderForm.name" placeholder="输入文件夹名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="folderDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitFolder">创建</el-button>
      </template>
    </el-dialog>

    <!-- 新建标签对话框 -->
    <el-dialog v-model="tagDialogVisible" title="新建标签" width="420px">
      <el-form label-width="80px">
        <el-form-item label="标签名称" required>
          <el-input v-model="tagForm.name" placeholder="输入标签名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="tagForm.color" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tagDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitTag">创建</el-button>
      </template>
    </el-dialog>

    <!-- 分配标签对话框 -->
    <el-dialog v-model="assignTagVisible" title="分配标签" width="480px">
      <el-checkbox-group v-model="assignTagIds">
        <el-checkbox v-for="tag in tagList" :key="tag.id" :value="tag.id" :label="tag.name" style="margin-bottom: 8px" />
      </el-checkbox-group>
      <el-empty v-if="!tagList.length" description="暂无标签,请先在左侧创建" :image-size="60" />
      <template #footer>
        <el-button @click="assignTagVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAssignTags">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新建自定义字段对话框 -->
    <el-dialog v-model="cfDialogVisible" title="新建自定义字段" width="480px">
      <el-form label-width="90px">
        <el-form-item label="字段名称" required>
          <el-input v-model="cfForm.name" placeholder="例如:测试环境、关联需求" />
        </el-form-item>
        <el-form-item label="字段类型">
          <el-select v-model="cfForm.field_type" style="width: 160px">
            <el-option label="文本" value="text" />
            <el-option label="数字" value="number" />
            <el-option label="下拉选择" value="select" />
            <el-option label="日期" value="date" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="cfForm.field_type === 'select'" label="选项">
          <el-input v-model="cfForm.options" placeholder="用逗号分隔,如:High,Medium,Low" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cfDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCf">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑自定义字段值对话框 -->
    <el-dialog v-model="editCfVisible" title="编辑自定义字段" width="520px">
      <el-form label-width="120px" v-if="customFields.length">
        <el-form-item v-for="cf in customFields" :key="cf.id" :label="cf.name">
          <el-input v-if="cf.field_type === 'text'" :model-value="getCfValue(cf.id)" @update:model-value="setCfValue(cf.id, $event)" :placeholder="'输入' + cf.name" />
          <el-input-number v-else-if="cf.field_type === 'number'" :model-value="Number(getCfValue(cf.id)) || 0" @update:model-value="setCfValue(cf.id, String($event))" />
          <el-select v-else-if="cf.field_type === 'select'" :model-value="getCfValue(cf.id)" @update:model-value="setCfValue(cf.id, $event)" placeholder="请选择" clearable>
            <el-option v-for="opt in getCfOptions(cf)" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-date-picker v-else-if="cf.field_type === 'date'" :model-value="getCfValue(cf.id)" @update:model-value="setCfValue(cf.id, $event)" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" />
          <el-input v-else :model-value="getCfValue(cf.id)" @update:model-value="setCfValue(cf.id, $event)" />
        </el-form-item>
      </el-form>
      <el-empty v-else description="暂无自定义字段" :image-size="60" />
      <template #footer>
        <el-button @click="editCfVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditCf">保存</el-button>
      </template>
    </el-dialog>

    </div>
  </div>
</template>

<style scoped>
.testcase-page {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.folder-sidebar {
  width: 240px;
  min-width: 240px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
}
.folder-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.folder-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.folder-tree {
  margin-bottom: 16px;
}
.folder-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
}
.folder-node:hover, .folder-node.active {
  background: #ecf5ff;
  color: #409eff;
}
.folder-tree-node {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  font-size: 13px;
}
.folder-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.folder-node-actions {
  display: none;
  gap: 2px;
}
.folder-tree-node:hover .folder-node-actions {
  display: inline-flex;
}
.folder-badge {
  margin-left: auto;
}
.folder-empty {
  text-align: center;
  color: #c0c4cc;
  font-size: 12px;
  padding: 12px 0;
}
.sidebar-section {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
  margin-top: 12px;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag-item {
  cursor: default;
}
.cf-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cf-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #606266;
}
.cf-item span {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.main-content {
  flex: 1;
  min-width: 0;
}
.stats {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  flex: 1;
  text-align: center;
}
.stat-num {
  font-size: 26px;
  font-weight: bold;
  color: #303133;
}
.stat-label {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
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
</style>
