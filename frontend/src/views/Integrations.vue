<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { integrationApi } from '../api'

const loading = ref(false)
const configs = ref([])

const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()
const form = reactive({
  id: null,
  name: '',
  type: '',
  system: '',
  enabled: true,
  config: {},
})

const rules = {
  name: [{ required: true, message: '请输入集成名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择集成类型', trigger: 'change' }],
  system: [{ required: true, message: '请选择目标系统', trigger: 'change' }],
}

const INTEGRATION_TYPES = [
  { label: '缺陷跟踪', value: 'defect_tracking' },
  { label: '通知渠道', value: 'notification' },
  { label: 'CI/CD', value: 'cicd' },
  { label: '自动化测试', value: 'automation' },
  { label: '代码仓库', value: 'code_repository' },
]

const SYSTEMS = {
  defect_tracking: [
    { label: 'Jira', value: 'jira' },
    { label: '禅道', value: 'zentao' },
    { label: 'Tapd', value: 'tapd' },
  ],
  notification: [
    { label: '钉钉', value: 'dingtalk' },
    { label: '企业微信', value: 'wecom' },
    { label: '飞书', value: 'feishu' },
    { label: '邮件', value: 'email' },
  ],
  cicd: [
    { label: 'Jenkins', value: 'jenkins' },
    { label: 'GitLab CI', value: 'gitlab_ci' },
    { label: 'GitHub Actions', value: 'github_actions' },
  ],
  automation: [
    { label: 'Selenium', value: 'selenium' },
    { label: 'Playwright', value: 'playwright' },
    { label: 'Cypress', value: 'cypress' },
    { label: 'JMeter', value: 'jmeter' },
  ],
  code_repository: [
    { label: 'GitLab', value: 'gitlab' },
    { label: 'GitHub', value: 'github' },
    { label: 'Bitbucket', value: 'bitbucket' },
  ],
}

async function load() {
  loading.value = true
  try {
    configs.value = await integrationApi.listConfigs()
  } catch (e) {
    configs.value = []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.id = null
  form.name = ''
  form.type = ''
  form.system = ''
  form.enabled = true
  form.config = {}
}

function openCreate() {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  Object.assign(form, row)
  dialogVisible.value = true
}

async function submit() {
  await formRef.value.validate()
  
  if (isEdit.value) {
    await integrationApi.updateConfig(form.id, form)
    ElMessage.success('修改成功')
  } else {
    await integrationApi.createConfig(form)
    ElMessage.success('创建成功')
  }
  
  dialogVisible.value = false
  load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除集成「${row.name}」?`, '提示', { type: 'warning' })
  await integrationApi.deleteConfig(row.id)
  ElMessage.success('已删除')
  load()
}

async function toggleEnabled(row) {
  await integrationApi.updateConfig(row.id, { enabled: !row.enabled })
  ElMessage.success(row.enabled ? '已启用' : '已禁用')
  load()
}

function getTypeLabel(type) {
  return INTEGRATION_TYPES.find(t => t.value === type)?.label || type
}

function getTypeTagType(type) {
  const map = {
    defect_tracking: 'danger',
    notification: 'warning',
    cicd: 'primary',
    automation: 'success',
    code_repository: 'info',
  }
  return map[type] || 'info'
}

function getSystemLabel(system, type) {
  const systems = SYSTEMS[type] || []
  return systems.find(s => s.value === system)?.label || system
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>新建集成
      </el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-alert
      title="外部集成配置"
      description="配置与外部工具(Jira/禅道/钉钉/Jenkins等)的集成,实现数据同步和自动化流程"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <el-table v-loading="loading" :data="configs" border stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="集成名称" min-width="160" />
      <el-table-column label="类型" width="120">
        <template #default="{ row }">
          <el-tag :type="getTypeTagType(row.type)" size="small">{{ getTypeLabel(row.type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="目标系统" width="120">
        <template #default="{ row }">{{ getSystemLabel(row.system, row.type) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? '已启用' : '已禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link :type="row.enabled ? 'warning' : 'success'" @click="toggleEnabled(row)">
            {{ row.enabled ? '禁用' : '启用' }}
          </el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑集成' : '新建集成'" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="集成名称" prop="name">
          <el-input v-model="form.name" placeholder="例如:Jira缺陷同步" />
        </el-form-item>
        <el-form-item label="集成类型" prop="type">
          <el-select v-model="form.type" placeholder="选择类型" style="width: 100%" @change="form.system = ''">
            <el-option v-for="t in INTEGRATION_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.type" label="目标系统" prop="system">
          <el-select v-model="form.system" placeholder="选择系统" style="width: 100%">
            <el-option v-for="s in SYSTEMS[form.type]" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="配置参数">
          <el-input
            v-model="form.config"
            type="textarea"
            :rows="6"
            placeholder='JSON 格式,例如:{"api_url":"https://jira.example.com","token":"xxx"}'
          />
          <div style="color: #909399; font-size: 12px; margin-top: 4px">
            注意:实际使用时需要解析为 JSON 对象
          </div>
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
.toolbar {
  margin-bottom: 16px;
  display: flex;
  gap: 10px;
}
</style>
