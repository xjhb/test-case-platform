<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi } from '../api'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()

const query = reactive({
  terminal_no: '',
  employee_name: '',
  join_date: '',
  page: 1,
  page_size: 20,
})

const form = reactive({
  id: null,
  username: '',
  password: '',
  display_name: '',
  employee_no: '',
  category: '',
  room: '',
  group: '',
  join_date: '',
  vendor: '',
  system_name: '',
  terminal_no: '',
  employment_status: '在职',
})

const rules = {
  username: [{ required: true, min: 3, message: '至少3个字符', trigger: 'blur' }],
  display_name: [{ required: true, message: '请输入员工姓名', trigger: 'blur' }],
}

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, page_size: query.page_size }
    if (query.terminal_no) params.terminal_no = query.terminal_no
    if (query.employee_name) params.employee_name = query.employee_name
    if (query.join_date) params.join_date = query.join_date
    const res = await userApi.listStaff(params)
    list.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function search() {
  query.page = 1
  load()
}

function resetQuery() {
  query.terminal_no = ''
  query.employee_name = ''
  query.join_date = ''
  search()
}

function openCreate() {
  isEdit.value = false
  form.id = null
  form.username = ''
  form.password = ''
  form.display_name = ''
  form.employee_no = ''
  form.category = ''
  form.room = ''
  form.group = ''
  form.join_date = ''
  form.vendor = ''
  form.system_name = ''
  form.terminal_no = ''
  form.employment_status = '在职'
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.id = row.id
  form.username = row.username
  form.password = ''
  form.display_name = row.display_name
  form.employee_no = row.employee_no
  form.category = row.category
  form.room = row.room
  form.group = row.group
  form.join_date = row.join_date
  form.vendor = row.vendor
  form.system_name = row.system_name
  form.terminal_no = row.terminal_no
  form.employment_status = row.employment_status
  dialogVisible.value = true
}

async function submit() {
  await formRef.value.validate()
  const payload = {
    display_name: form.display_name,
    employee_no: form.employee_no,
    category: form.category,
    room: form.room,
    group: form.group,
    join_date: form.join_date || null,
    vendor: form.vendor,
    system_name: form.system_name,
    terminal_no: form.terminal_no,
    employment_status: form.employment_status,
  }
  if (isEdit.value) {
    await userApi.update(form.id, payload)
    ElMessage.success('修改成功')
  } else {
    await userApi.create({ username: form.username, password: form.password, ...payload })
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false
  load()
}

async function toggleStatus(row) {
  await userApi.update(row.id, { employment_status: row.employment_status === '在职' ? '离职' : '在职' })
  ElMessage.success('已更新')
  load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除「${row.display_name}」?`, '提示', { type: 'warning' })
  await userApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

// ---- 重置密码 ----
const tempVisible = ref(false)
const tempData = reactive({ username: '', display_name: '', temp_password: '' })

async function resetPassword(row) {
  await ElMessageBox.confirm(
    `确定重置「${row.display_name || row.username}」的密码?\n\n` +
    `系统将生成一个随机临时密码,该密码只显示一次。\n` +
    `对方下次登录后会被要求立即修改密码。`,
    '重置密码',
    { type: 'warning', confirmButtonText: '确定重置', cancelButtonText: '取消' }
  )
  const res = await userApi.resetPassword(row.id)
  tempData.username = res.username
  tempData.display_name = res.display_name || ''
  tempData.temp_password = res.temp_password
  tempVisible.value = true
  ElMessage.success('已生成临时密码')
  load()
}

async function copyTemp() {
  try {
    await navigator.clipboard.writeText(tempData.temp_password)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败,请手动选中复制')
  }
}

function pageChange(p) { query.page = p; load() }
function sizeChange(s) { query.page_size = s; query.page = 1; load() }

onMounted(load)
</script>

<template>
  <div>
    <!-- 筛选行 -->
    <div class="filter-row">
      <el-input v-model="query.terminal_no" placeholder="终端号" clearable style="width: 160px" @keyup.enter="search" />
      <el-input v-model="query.employee_name" placeholder="员工姓名" clearable style="width: 160px" @keyup.enter="search" />
      <el-input v-model="query.join_date" placeholder="入职时间" clearable style="width: 160px" @keyup.enter="search" />
      <el-button type="primary" @click="search">
        <el-icon><Search /></el-icon>搜索
      </el-button>
      <el-button @click="resetQuery">重置</el-button>
      <el-button type="primary" @click="openCreate" style="margin-left: auto">
        <el-icon><Plus /></el-icon>新增人员
      </el-button>
    </div>

    <!-- 表格(Excel风格表头) -->
    <el-table v-loading="loading" :data="list" border stripe :header-cell-style="{ background: '#f5f7fa', color: '#303133', fontWeight: 600 }">
      <el-table-column type="index" label="序号" width="60" align="center" />
      <el-table-column prop="employee_no" label="员工编号" width="110" />
      <el-table-column prop="display_name" label="员工姓名" width="100" />
      <el-table-column prop="category" label="员工类别" width="100" />
      <el-table-column prop="room" label="室" width="80" />
      <el-table-column prop="group" label="组" width="80" />
      <el-table-column prop="join_date" label="入职时间" width="110" />
      <el-table-column prop="vendor" label="供应商名称" width="140" show-overflow-tooltip />
      <el-table-column prop="system_name" label="系统名称" width="120" show-overflow-tooltip />
      <el-table-column label="在职状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.employment_status === '在职' ? 'success' : 'info'" size="small">{{ row.employment_status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="warning" @click="toggleStatus(row)">{{ row.employment_status === '在职' ? '离职' : '复职' }}</el-button>
          <el-button link type="info" @click="resetPassword(row)">重置密码</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pager"
      :total="total"
      :current-page="query.page"
      :page-size="query.page_size"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="pageChange"
      @size-change="sizeChange"
    />

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑人员' : '新增人员'" width="680px" top="6vh">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username" v-if="!isEdit">
              <el-input v-model="form.username" placeholder="登录用户名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码" prop="password" v-if="!isEdit" :rules="[{ required: true, min: 6, message: '至少6位', trigger: 'blur' }]">
              <el-input v-model="form.password" type="password" show-password placeholder="登录密码" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="员工姓名" prop="display_name">
              <el-input v-model="form.display_name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="员工编号">
              <el-input v-model="form.employee_no" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="员工类别">
              <el-input v-model="form.category" placeholder="如:测试" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="室">
              <el-input v-model="form.room" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="组">
              <el-input v-model="form.group" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="入职时间">
              <el-date-picker v-model="form.join_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="终端号">
              <el-input v-model="form.terminal_no" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="在职状态">
              <el-select v-model="form.employment_status" style="width: 100%">
                <el-option label="在职" value="在职" />
                <el-option label="离职" value="离职" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="供应商名称">
              <el-input v-model="form.vendor" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="系统名称">
              <el-input v-model="form.system_name" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 临时密码展示(仅显示一次) -->
    <el-dialog v-model="tempVisible" title="临时密码已生成" width="520px" :close-on-click-modal="false">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="此密码仅显示这一次"
        description="关闭本窗口后无法再次查看。请立即复制并线下转交给本人。对方下次登录时会被要求修改密码。"
      />
      <div class="temp-box">
        <div class="temp-row">
          <span class="temp-label">用户</span>
          <span class="temp-value">{{ tempData.display_name }}（{{ tempData.username }}）</span>
        </div>
        <div class="temp-row">
          <span class="temp-label">临时密码</span>
          <code class="temp-pwd">{{ tempData.temp_password }}</code>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="copyTemp">复制密码</el-button>
        <el-button @click="tempVisible = false">我已保存,关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.filter-row {
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
.temp-box {
  margin-top: 16px;
  background: #f5f7fa;
  border-radius: 6px;
  padding: 14px 16px;
}
.temp-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}
.temp-label {
  width: 72px;
  color: #909399;
  font-size: 13px;
  flex-shrink: 0;
}
.temp-value {
  color: #303133;
  font-size: 14px;
}
.temp-pwd {
  font-family: Consolas, Monaco, monospace;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #409eff;
  background: #fff;
  border: 1px dashed #c0c4cc;
  border-radius: 4px;
  padding: 6px 14px;
  user-select: all;
}
</style>
