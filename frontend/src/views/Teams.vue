<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { teamApi } from '../api'

const router = useRouter()
const teams = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()
const allUsers = ref([])

const form = reactive({ id: null, name: '', system: '', description: '', leader_id: '' })
const rules = { name: [{ required: true, message: '请输入团队名称', trigger: 'blur' }] }

async function load() {
  loading.value = true
  try {
    teams.value = await teamApi.list()
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  allUsers.value = await teamApi.usersForSelect()
}

function openCreate() {
  isEdit.value = false
  form.id = null
  form.name = ''
  form.system = ''
  form.description = ''
  form.leader_id = ''
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  form.id = row.id
  form.name = row.name
  form.system = row.system
  form.description = row.description
  form.leader_id = row.leader_id || ''
  dialogVisible.value = true
}

async function submit() {
  await formRef.value.validate()
  const payload = {
    name: form.name,
    system: form.system,
    description: form.description,
    leader_id: form.leader_id || null,
  }
  if (isEdit.value) {
    await teamApi.update(form.id, payload)
    ElMessage.success('修改成功')
  } else {
    await teamApi.create(payload)
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false
  load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除团队「${row.name}」?`, '提示', { type: 'warning' })
  await teamApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

function goMembers(row) {
  router.push({ name: 'team-members', params: { id: row.id } })
}

onMounted(async () => {
  await loadUsers()
  load()
})
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>新建团队
      </el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="teams" border stripe>
      <el-table-column prop="id" label="编号" width="70" />
      <el-table-column prop="name" label="团队名称" min-width="140" />
      <el-table-column prop="system" label="所属系统" width="140" show-overflow-tooltip />
      <el-table-column prop="description" label="团队说明" min-width="180" show-overflow-tooltip />
      <el-table-column prop="leader_name" label="团队负责人" width="120" />
      <el-table-column prop="member_count" label="成员数" width="80" align="center" />
      <el-table-column prop="created_by_name" label="创建人" width="100" />
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
      </el-table-column>
      <el-table-column prop="updated_at" label="最后更新时间" width="170">
        <template #default="{ row }">{{ new Date(row.updated_at).toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="success" @click="goMembers(row)">团队成员</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑团队' : '新建团队'" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="团队名称" prop="name">
          <el-input v-model="form.name" placeholder="如:测试一组" />
        </el-form-item>
        <el-form-item label="所属系统">
          <el-input v-model="form.system" placeholder="如:订单系统" />
        </el-form-item>
        <el-form-item label="团队说明">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="团队职责描述" />
        </el-form-item>
        <el-form-item label="团队负责人">
          <el-select v-model="form.leader_id" placeholder="选择负责人" clearable filterable style="width: 100%">
            <el-option v-for="u in allUsers" :key="u.id" :label="u.display_name + ' (' + u.username + ')'" :value="u.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; gap: 10px; }
</style>
