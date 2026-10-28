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
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
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
          <el-select v-model="form.project_id" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="指派人">
          <el-select v-model="form.assignee_id" clearable style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" v-if="isEdit">
          <el-select v-model="form.status" style="width: 100%">
            <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { defectApi, projectApi, userApi } from '../api'

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
const role = ref(localStorage.getItem('role') || 'member')

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
  assignee_id: null,
  status: '新建',
})

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
    users.value = await userApi.list()
  } catch (e) { console.error(e) }
}

const showCreateDialog = () => {
  isEdit.value = false
  Object.assign(form, { title: '', description: '', severity: '一般', priority: 'P1', project_id: null, assignee_id: null, status: '新建' })
  dialogVisible.value = true
}

const showEditDialog = (row) => {
  isEdit.value = true
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

onMounted(() => {
  loadData()
  loadProjects()
  loadUsers()
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
</style>
