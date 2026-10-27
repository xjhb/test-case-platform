<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { teamApi, projectApi } from '../api'

const route = useRoute()
const router = useRouter()
const teamId = Number(route.params.id)
const loading = ref(false)
const members = ref([])
const team = ref(null)
const allUsers = ref([])
const projects = ref([])

const addVisible = ref(false)
const addFormRef = ref()
const addForm = reactive({ user_id: '', department: '' })
const addRules = { user_id: [{ required: true, message: '请选择成员', trigger: 'change' }] }

const roleLabel = (r) => ({ admin: '管理员', member: '外包人员' }[r] || r)

async function load() {
  loading.value = true
  try {
    teams.value = await teamApi.list()
    team.value = (await teamApi.list()).find((t) => t.id === teamId)
    members.value = await teamApi.members(teamId)
    // 过滤掉已在团队的成员
    allUsers.value = (await teamApi.usersForSelect()).filter(
      (u) => !members.value.some((m) => m.id === u.id)
    )
  } finally {
    loading.value = false
  }
}

var teams = ref([])

async function loadProjects() {
  projects.value = await projectApi.list()
}

function projNames(ids) {
  return (ids || [])
    .map((id) => projects.value.find((p) => p.id === id)?.name || `#${id}`)
    .join('、') || '无'
}

function openAdd() {
  addForm.user_id = ''
  addForm.department = ''
  addVisible.value = true
}

async function submitAdd() {
  await addFormRef.value.validate()
  await teamApi.addMember(teamId, { user_id: addForm.user_id, department: addForm.department })
  ElMessage.success('成员已添加')
  addVisible.value = false
  load()
}

async function removeMember(row) {
  await ElMessageBox.confirm(`确定将「${row.display_name}」移出团队?`, '提示', { type: 'warning' })
  await teamApi.removeMember(teamId, row.id)
  ElMessage.success('已移出')
  load()
}

onMounted(async () => {
  await loadProjects()
  load()
})
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="router.push({ name: 'teams' })">
        <el-icon><Back /></el-icon>返回团队列表
      </el-button>
      <span v-if="team" class="team-title">团队:{{ team.name }} | {{ team.system }}</span>
      <el-button type="primary" @click="openAdd" style="margin-left: auto">
        <el-icon><Plus /></el-icon>添加成员
      </el-button>
    </div>

    <el-table v-loading="loading" :data="members" border stripe>
      <el-table-column prop="id" label="编号" width="70" />
      <el-table-column prop="username" label="用户名" width="120" />
      <el-table-column prop="display_name" label="用户姓名" width="120" />
      <el-table-column label="所属角色" width="100">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'warning' : 'info'" size="small">{{ roleLabel(row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="department" label="部门" width="140" show-overflow-tooltip />
      <el-table-column label="关联项目" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ projNames(row.project_ids) }}</template>
      </el-table-column>
      <el-table-column label="是否团队负责人" width="130" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_leader" type="success" size="small">是</el-tag>
          <el-tag v-else type="info" size="small">否</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" @click="removeMember(row)">移出</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !members.length" description="暂无团队成员" />

    <!-- 添加成员 -->
    <el-dialog v-model="addVisible" title="添加团队成员" width="460px">
      <el-form ref="addFormRef" :model="addForm" :rules="addRules" label-width="80px">
        <el-form-item label="成员" prop="user_id">
          <el-select v-model="addForm.user_id" placeholder="选择用户" filterable style="width: 100%">
            <el-option v-for="u in allUsers" :key="u.id" :label="u.display_name + ' (' + u.username + ')'" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="addForm.department" placeholder="如:测试一部" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; gap: 10px; }
.team-title { font-size: 16px; font-weight: 600; color: #303133; }
</style>
