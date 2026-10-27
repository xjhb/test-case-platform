<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectApi, p2Api, userApi } from '../api'

const router = useRouter()
const list = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()

const form = reactive({
  id: null, name: '', description: '', project_no: '', level: '',
  project_type: '', test_manager: '', tech_manager: '', sa: '',
  is_key_project: false, is_started: false,
})

const rules = { name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }] }

async function load() {
  loading.value = true
  try { list.value = await projectApi.list() } finally { loading.value = false }
}

function resetForm() {
  form.id = null; form.name = ''; form.description = ''; form.project_no = ''
  form.level = ''; form.project_type = ''; form.test_manager = ''
  form.tech_manager = ''; form.sa = ''; form.is_key_project = false; form.is_started = false
}

function openCreate() {
  isEdit.value = false; resetForm(); dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  Object.assign(form, row)
  dialogVisible.value = true
}

async function submit() {
  await formRef.value.validate()
  if (isEdit.value) {
    await projectApi.update(form.id, { ...form })
    ElMessage.success('修改成功')
  } else {
    await projectApi.create({ ...form })
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false; load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除项目「${row.name}」?`, '提示', { type: 'warning' })
  await projectApi.remove(row.id)
  ElMessage.success('已删除'); load()
}

async function toggleStar(row) {
  await projectApi.toggleStar(row.id)
  row.starred = !row.starred
}

function openRounds(row) {
  router.push({
    name: 'plans',
    query: { project_id: row.id, project_no: row.project_no, project_name: row.name },
  })
}

// ---- RBAC 项目角色管理 ----
const roleVisible = ref(false)
const roleProject = ref(null)
const roleList = ref([])
const roleLoading = ref(false)
const assignRoleVisible = ref(false)
const assignRoleForm = reactive({ user_id: '', role: 'tester' })
const userList = ref([])
const ROLE_OPTIONS = [
  { label: '管理员(manager)', value: 'manager' },
  { label: '测试负责人(test_lead)', value: 'test_lead' },
  { label: '测试员(tester)', value: 'tester' },
  { label: '只读(viewer)', value: 'viewer' },
]

async function openRoleDialog(row) {
  roleProject.value = row
  roleVisible.value = true
  await loadRoles()
}

async function loadRoles() {
  if (!roleProject.value) return
  roleLoading.value = true
  try {
    roleList.value = await p2Api.listRoles(roleProject.value.id)
  } catch (e) {
    roleList.value = []
  } finally {
    roleLoading.value = false
  }
}

async function openAssignRole() {
  assignRoleForm.user_id = ''
  assignRoleForm.role = 'tester'
  assignRoleVisible.value = true
  try {
    userList.value = await userApi.list()
  } catch (e) {
    userList.value = []
  }
}

async function submitAssignRole() {
  if (!assignRoleForm.user_id) {
    ElMessage.warning('请选择用户')
    return
  }
  await p2Api.assignRole(roleProject.value.id, {
    user_id: Number(assignRoleForm.user_id),
    role: assignRoleForm.role,
  })
  ElMessage.success('角色已分配')
  assignRoleVisible.value = false
  loadRoles()
}

async function removeRole(row) {
  await ElMessageBox.confirm(`确定移除用户「${row.display_name || row.username}」的项目角色?`, '提示', { type: 'warning' })
  await p2Api.removeRole(roleProject.value.id, row.user_id)
  ElMessage.success('已移除')
  loadRoles()
}

function roleLabel(r) {
  return { manager: '管理员', test_lead: '测试负责人', tester: '测试员', viewer: '只读' }[r] || r
}

function roleTagType(r) {
  return { manager: 'danger', test_lead: 'warning', tester: 'primary', viewer: 'info' }[r] || 'info'
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="openCreate"><el-icon><Plus /></el-icon>新建项目</el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column type="index" label="序号" width="60" align="center" />
      <el-table-column label="关注" width="60" align="center">
        <template #default="{ row }">
          <el-icon :size="20" style="cursor: pointer" :color="row.starred ? '#f7ba2a' : '#c0c4cc'" @click="toggleStar(row)">
            <StarFilled v-if="row.starred" /><Star v-else />
          </el-icon>
        </template>
      </el-table-column>
      <el-table-column prop="project_no" label="项目编号" width="110" />
      <el-table-column prop="name" label="项目名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="level" label="项目等级" width="90" align="center" />
      <el-table-column prop="project_type" label="项目类型" width="100" />
      <el-table-column prop="test_manager" label="测试经理" width="90" />
      <el-table-column prop="tech_manager" label="技术经理" width="90" />
      <el-table-column prop="sa" label="SA" width="80" />
      <el-table-column label="重点项目" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_key_project" type="danger" size="small">是</el-tag>
          <span v-else style="color: #c0c4cc">否</span>
        </template>
      </el-table-column>
      <el-table-column label="启动状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_started" type="success" size="small">是</el-tag>
          <el-tag v-else type="info" size="small">否</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openRounds(row)">打开轮次</el-button>
          <el-button link type="warning" @click="openRoleDialog(row)">角色管理</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑项目' : '新建项目'" width="640px" top="6vh">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="项目名称" prop="name"><el-input v-model="form.name" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="项目编号"><el-input v-model="form.project_no" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="项目等级"><el-select v-model="form.level" style="width:100%"><el-option label="A" value="A" /><el-option label="B" value="B" /><el-option label="C" value="C" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="项目类型"><el-input v-model="form.project_type" placeholder="如:Web" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="描述"><el-input v-model="form.description" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="测试经理"><el-input v-model="form.test_manager" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="技术经理"><el-input v-model="form.tech_manager" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="SA"><el-input v-model="form.sa" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="重点项目"><el-switch v-model="form.is_key_project" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="启动状态"><el-switch v-model="form.is_started" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 角色管理对话框 -->
    <el-dialog v-model="roleVisible" :title="`角色管理 - ${roleProject?.name || ''}`" width="680px">
      <div class="toolbar" style="margin-bottom: 12px">
        <el-button type="primary" size="small" @click="openAssignRole">
          <el-icon><Plus /></el-icon>分配角色
        </el-button>
        <el-button size="small" @click="loadRoles">刷新</el-button>
      </div>
      <el-table v-loading="roleLoading" :data="roleList" border size="small">
        <el-table-column prop="user_id" label="用户ID" width="80" />
        <el-table-column label="用户名" width="120">
          <template #default="{ row }">{{ row.display_name || row.username }}</template>
        </el-table-column>
        <el-table-column label="角色" width="140">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)" size="small">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeRole(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!roleLoading && !roleList.length" description="暂无角色分配" :image-size="60" />
    </el-dialog>

    <!-- 分配角色对话框 -->
    <el-dialog v-model="assignRoleVisible" title="分配项目角色" width="460px">
      <el-form label-width="80px">
        <el-form-item label="用户" required>
          <el-select v-model="assignRoleForm.user_id" placeholder="选择用户" filterable style="width: 100%">
            <el-option v-for="u in userList" :key="u.id" :label="`${u.display_name || u.username} (${u.username})`" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="assignRoleForm.role" style="width: 100%">
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignRoleVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAssignRole">分配</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; gap: 10px; }
</style>
