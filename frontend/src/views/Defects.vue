<template>
  <div class="defects-page">
    <div class="page-header">
      <h2>缺陷管理</h2>
      <el-button type="primary" @click="showCreateDialog">新建缺陷</el-button>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.project_id" placeholder="所属项目" clearable style="width: 180px" @change="loadData">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 120px" @change="loadData">
        <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="filters.severity" placeholder="严重程度" clearable style="width: 120px" @change="loadData">
        <el-option v-for="s in severityOptions" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="filters.priority" placeholder="优先级" clearable style="width: 100px" @change="loadData">
        <el-option v-for="p in priorityOptions" :key="p" :label="p" :value="p" />
      </el-select>
      <el-input v-model="filters.keyword" placeholder="搜索标题/描述" clearable style="width: 200px" @keyup.enter="loadData" />
      <el-button type="primary" @click="loadData">搜索</el-button>
    </div>

    <el-table :data="defects" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="severity" label="严重程度" width="100">
        <template #default="{ row }">
          <el-tag :type="severityTagType(row.severity)" size="small">{{ row.severity }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级" width="80" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reporter_name" label="提交人" width="100" />
      <el-table-column prop="assignee_name" label="指派人" width="100" />
      <el-table-column prop="created_at" label="创建时间" width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="330" fixed="right">
        <template #default="{ row }">
          <el-dropdown v-if="nextStatuses(row).length" trigger="click" @command="(s) => changeStatus(row, s)">
            <el-button size="small" type="primary" plain>流转</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="s in nextStatuses(row)" :key="s" :command="s">{{ s }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" @click="showAttachments(row)">附件{{ attachmentCounts[row.id] ? `(${attachmentCounts[row.id]})` : '' }}</el-button>
          <el-button size="small" @click="showTrace(row)">来源</el-button>
          <el-button size="small" @click="showEditDialog(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)" v-if="role === 'admin'">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > 0"
      class="pagination"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="handlePageChange"
    />

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑缺陷' : '新建缺陷'" width="600px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="严重程度">
          <el-select v-model="form.severity" style="width: 100%">
            <el-option v-for="s in severityOptions" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width: 100%">
            <el-option v-for="p in priorityOptions" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属项目" v-if="!isEdit">
          <el-select v-model="form.project_id" style="width: 100%" @change="loadProjectTestcases">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联用例" v-if="!isEdit">
          <el-select v-model="form.testcase_id" placeholder="可选,追溯到具体用例" clearable filterable style="width: 100%">
            <el-option v-for="tc in testcaseOptions" :key="tc.id" :label="`#${tc.id} ${tc.title}`" :value="tc.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="指派人">
          <el-select v-model="form.assignee_id" clearable style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" v-if="isEdit">
          <el-select v-model="form.status" style="width: 100%">
            <el-option v-for="s in editStatusOptions" :key="s" :label="s" :value="s" />
          </el-select>
          <div class="form-tip">当前状态「{{ originalStatus }}」,按状态机只可流转到: {{ nextStatuses({ status: originalStatus }).join('、') || '无' }}。管理员可强制流转。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 缺陷来源追溯 -->
    <el-dialog v-model="traceVisible" :title="traceTitle" width="640px">
      <div v-loading="traceLoading">
        <el-descriptions :column="1" border size="small" class="trace-desc">
          <el-descriptions-item label="来源用例">
            <template v-if="traceData.testcase">
              #{{ traceData.testcase.id }} {{ traceData.testcase.title }}
              <el-tag size="small" type="info" style="margin-left: 6px">{{ traceData.testcase.module || '-' }}</el-tag>
              <el-tag :type="tcStatusType(traceData.testcase.status)" size="small" style="margin-left: 4px">{{ traceData.testcase.status }}</el-tag>
            </template>
            <span v-else style="color: #c0c4cc">未关联用例</span>
          </el-descriptions-item>
          <el-descriptions-item label="来源执行记录">
            <template v-if="traceData.run">
              #{{ traceData.run.id }}
              <el-tag :type="tcStatusType(traceData.run.status)" size="small" style="margin-left: 6px">{{ traceData.run.status }}</el-tag>
              <el-tag size="small" style="margin-left: 4px">{{ traceData.run.stage || '-' }}</el-tag>
              <span style="margin-left: 6px">{{ traceData.run.executed_by || '-' }}</span>
              <span style="margin-left: 6px; color: #909399">{{ traceData.run.executed_at ? new Date(traceData.run.executed_at).toLocaleString('zh-CN') : '' }}</span>
              <div v-if="traceData.run.remark" style="color: #606266; margin-top: 4px">备注: {{ traceData.run.remark }}</div>
            </template>
            <span v-else style="color: #c0c4cc">未关联执行记录</span>
          </el-descriptions-item>
          <el-descriptions-item label="所属测试计划">
            <template v-if="traceData.plan">
              #{{ traceData.plan.id }} {{ traceData.plan.version }}
              <el-tag size="small" style="margin-left: 6px">{{ traceData.plan.current_stage || '-' }}</el-tag>
              <el-tag :type="traceData.plan.status === '已完成' ? 'success' : 'warning'" size="small" style="margin-left: 4px">{{ traceData.plan.status }}</el-tag>
            </template>
            <span v-else style="color: #c0c4cc">未关联计划</span>
          </el-descriptions-item>
          <el-descriptions-item label="外部工单">
            <template v-if="externalLinks.length">
              <div v-for="l in externalLinks" :key="l.id" class="ext-link">
                <el-tag size="small">{{ l.system }}</el-tag>
                <span style="margin-left: 6px">{{ l.external_id }}</span>
                <el-tag size="small" type="info" style="margin-left: 6px">{{ l.synced_status || '-' }}</el-tag>
                <a v-if="l.external_url" :href="l.external_url" target="_blank" rel="noopener" style="margin-left: 6px">打开</a>
              </div>
            </template>
            <span v-else style="color: #c0c4cc">未推送</span>
          </el-descriptions-item>
        </el-descriptions>
        <div class="ext-actions">
          <span style="color: #909399; font-size: 12px">推送到外部系统需先在「外部工具集成」页面完成凭据配置;未配置时接口返回 503 并列出缺失项。</span>
          <el-button size="small" :loading="pushing === 'jira'" @click="handlePush('jira')">推送到 Jira</el-button>
          <el-button size="small" :loading="pushing === 'zentao'" @click="handlePush('zentao')">推送到禅道</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="traceVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 缺陷附件 -->
    <el-dialog v-model="attachVisible" :title="attachTitle" width="720px">
      <div v-loading="attachLoading">
        <el-upload
          :show-file-list="false"
          :http-request="handleUpload"
          :before-upload="beforeUpload"
          multiple
          drag
          class="attach-upload"
        >
          <div class="attach-drop">
            <div>将日志、截图、文档拖到此处,或<em>点击上传</em></div>
            <div class="attach-tip">单个附件不超过 20MB,支持 png/jpg/gif/webp/txt/log/csv/json/xml/har/pdf/office/压缩包</div>
          </div>
        </el-upload>

        <el-table :data="attachments" size="small" stripe style="margin-top: 12px">
          <el-table-column label="文件名" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <el-image
                v-if="isImage(row)"
                :src="row.url"
                :preview-src-list="[row.url]"
                fit="cover"
                style="width: 28px; height: 28px; margin-right: 8px; vertical-align: middle"
              />
              <span style="vertical-align: middle">{{ row.original_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="100">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column prop="uploaded_by_name" label="上传人" width="100" />
          <el-table-column label="上传时间" width="160">
            <template #default="{ row }">{{ formatDate(row.uploaded_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="handleDownload(row)">下载</el-button>
              <el-button size="small" type="danger" @click="handleDeleteAttachment(row)" v-if="canDeleteAttachment(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无附件</template>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="attachVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { defectApi, integrationApi, projectApi, userApi, testcaseApi } from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const defects = ref([])
const projects = ref([])
const users = ref([])
const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const auth = useAuthStore()
const role = computed(() => auth.role)

const statusOptions = ['新建', '处理中', '已修复', '已验证', '关闭', '重新打开']
const severityOptions = ['致命', '严重', '一般', '提示']
const priorityOptions = ['P0', 'P1', 'P2', 'P3']

const filters = reactive({
  project_id: null,
  status: null,
  severity: null,
  priority: null,
  keyword: '',
})

const form = reactive({
  title: '',
  description: '',
  severity: '一般',
  priority: 'P1',
  project_id: null,
  testcase_id: null,
  assignee_id: null,
  status: '新建',
})

const testcaseOptions = ref([])

// ---- 状态机 ----
const statusTransitions = ref({})
const originalStatus = ref('')

const loadStatusFlow = async () => {
  try {
    const res = await defectApi.statusFlow()
    statusTransitions.value = res.transitions || {}
  } catch (e) { console.error(e) }
}

const nextStatuses = (row) => statusTransitions.value[row?.status] || []

const editStatusOptions = computed(() => {
  if (!originalStatus.value) return statusOptions
  if (role.value === 'admin') return statusOptions
  return [originalStatus.value, ...nextStatuses({ status: originalStatus.value })]
})

const changeStatus = async (row, status) => {
  try {
    await defectApi.update(row.id, { status })
    ElMessage.success(`已流转到「${status}」`)
    loadData()
  } catch (e) {
    console.error(e)
  }
}

const loadProjectTestcases = async (pid) => {
  testcaseOptions.value = []
  form.testcase_id = null
  if (!pid) return
  try {
    const res = await testcaseApi.list({ project_id: pid, page_size: 200 })
    testcaseOptions.value = res.items || []
  } catch (e) { console.error(e) }
}

const severityTagType = (s) => {
  const map = { '致命': 'danger', '严重': 'warning', '一般': 'info', '提示': 'success' }
  return map[s] || 'info'
}

const statusTagType = (s) => {
  const map = { '新建': 'danger', '处理中': 'warning', '已修复': 'success', '已验证': 'success', '关闭': 'info', '重新打开': 'danger' }
  return map[s] || 'info'
}

const formatDate = (d) => {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN')
}

const loadData = async () => {
  loading.value = true
  try {
    const params = { page: page.value, size: pageSize.value }
    if (filters.project_id) params.project_id = filters.project_id
    if (filters.status) params.status = filters.status
    if (filters.severity) params.severity = filters.severity
    if (filters.priority) params.priority = filters.priority
    if (filters.keyword) params.keyword = filters.keyword
    const res = await defectApi.list(params)
    defects.value = Array.isArray(res) ? res : (res.items || [])
    total.value = res.total || defects.value.length
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const loadProjects = async () => {
  try {
    projects.value = await projectApi.list()
  } catch (e) { console.error(e) }
}

const loadUsers = async () => {
  try {
    users.value = await userApi.options()
  } catch (e) { console.error(e) }
}

const showCreateDialog = () => {
  isEdit.value = false
  originalStatus.value = ''
  Object.assign(form, { title: '', description: '', severity: '一般', priority: 'P1', project_id: null, testcase_id: null, assignee_id: null, status: '新建' })
  testcaseOptions.value = []
  dialogVisible.value = true
}

const showEditDialog = (row) => {
  isEdit.value = true
  originalStatus.value = row.status
  Object.assign(form, { ...row })
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!form.title) {
    ElMessage.warning('请填写标题')
    return
  }
  submitting.value = true
  try {
    if (isEdit.value) {
      await defectApi.update(form.id, {
        title: form.title,
        description: form.description,
        severity: form.severity,
        priority: form.priority,
        status: form.status,
        assignee_id: form.assignee_id,
      })
      ElMessage.success('更新成功')
    } else {
      if (!form.project_id) {
        ElMessage.warning('请选择所属项目')
        return
      }
      await defectApi.create({
        title: form.title,
        description: form.description,
        severity: form.severity,
        priority: form.priority,
        project_id: form.project_id,
        testcase_id: form.testcase_id,
        assignee_id: form.assignee_id,
      })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadData()
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除缺陷「${row.title}」?`, '提示', { type: 'warning' })
    await defectApi.remove(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}

const handlePageChange = (p) => {
  page.value = p
  loadData()
}

// ---- 来源追溯 ----
const traceVisible = ref(false)
const traceLoading = ref(false)
const traceTitle = ref('')
const traceData = ref({ testcase: null, run: null, plan: null })
const traceRow = ref(null)
const externalLinks = ref([])
const pushing = ref('')

const tcStatusType = (s) => ({ 未执行: 'info', 通过: 'success', 失败: 'danger', 阻塞: 'warning' }[s] || 'info')

const showTrace = async (row) => {
  traceTitle.value = `缺陷来源 - ${row.title}`
  traceRow.value = row
  externalLinks.value = []
  traceVisible.value = true
  traceLoading.value = true
  try {
    traceData.value = await defectApi.traceability(row.id)
    externalLinks.value = await integrationApi.defectLinks(row.id)
  } catch (e) {
    console.error(e)
  } finally {
    traceLoading.value = false
  }
}

const handlePush = async (system) => {
  if (!traceRow.value) return
  pushing.value = system
  try {
    const res = await integrationApi.pushDefect(traceRow.value.id, system)
    ElMessage.success(res.message || `已推送到 ${system}`)
    externalLinks.value = await integrationApi.defectLinks(traceRow.value.id)
  } catch (e) {
    // 拦截器已提示后端 detail(未配置 503 / 远端失败 502),这里不再重复弹
  } finally {
    pushing.value = ''
  }
}

// ---- 附件 ----
const attachVisible = ref(false)
const attachLoading = ref(false)
const attachTitle = ref('')
const attachRow = ref(null)
const attachments = ref([])
const attachmentCounts = computed(() => {
  const map = {}
  defects.value.forEach((d) => { if (d.attachment_count) map[d.id] = d.attachment_count })
  return map
})

const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp']
const isImage = (row) => IMAGE_EXTS.includes((row.original_name || '').split('.').pop().toLowerCase())

const formatSize = (n) => {
  if (!n) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const canDeleteAttachment = (row) => row.can_delete

const loadAttachments = async () => {
  if (!attachRow.value) return
  attachLoading.value = true
  try {
    attachments.value = await defectApi.attachments(attachRow.value.id)
  } catch (e) {
    console.error(e)
  } finally {
    attachLoading.value = false
  }
}

const showAttachments = (row) => {
  attachRow.value = row
  attachTitle.value = `缺陷附件 - ${row.title}`
  attachments.value = []
  attachVisible.value = true
  loadAttachments()
}

const beforeUpload = (file) => {
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.warning('附件不能超过 20MB')
    return false
  }
  return true
}

const handleUpload = async ({ file }) => {
  if (!attachRow.value) return
  try {
    await defectApi.uploadAttachment(attachRow.value.id, file)
    ElMessage.success(`${file.name} 上传成功`)
    await Promise.all([loadAttachments(), loadData()])
  } catch (e) {
    console.error(e)
  }
}

const handleDownload = async (row) => {
  try {
    const blob = await defectApi.downloadAttachment(row.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = row.original_name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    // 附件文件丢失时后端返回 404,拦截器拿不到 detail(blob),这里兜底提示
    ElMessage.error('下载失败,附件文件可能已丢失')
  }
}

const handleDeleteAttachment = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除附件「${row.original_name}」?`, '提示', { type: 'warning' })
    await defectApi.deleteAttachment(row.id)
    ElMessage.success('删除成功')
    await Promise.all([loadAttachments(), loadData()])
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}

onMounted(async () => {
  loadProjects()
  loadUsers()
  loadStatusFlow()
  await loadData()
  // 通知里的"查看详情"带 focus=<缺陷ID>,直接打开来源追溯
  const focus = Number(route.query.focus)
  if (focus) {
    showTrace(defects.value.find((d) => d.id === focus) || { id: focus, title: `缺陷#${focus}` })
  }
})
</script>

<style scoped>
.defects-page {
  padding: 20px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0;
  font-size: 20px;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
.ext-link {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}
.ext-actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.form-tip {
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
}
.attach-upload {
  width: 100%;
}
.attach-drop {
  padding: 8px 0;
  color: #606266;
}
.attach-drop em {
  color: #409eff;
  font-style: normal;
}
.attach-tip {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
