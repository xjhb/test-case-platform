<template>
  <div class="reports-page">
    <div class="page-header">
      <h2>测试报告</h2>
      <el-button type="primary" @click="showGenerateDialog">生成报告</el-button>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.project_id" placeholder="所属项目" clearable style="width: 200px" @change="loadData">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="filters.plan_id" placeholder="测试计划" clearable style="width: 200px" @change="loadData">
        <el-option v-for="pl in plans" :key="pl.id" :label="`${pl.version}`" :value="pl.id" />
      </el-select>
    </div>

    <el-table :data="reports" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="报告标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="stage" label="阶段" width="80">
        <template #default="{ row }">
          <el-tag size="small">{{ row.stage }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total_cases" label="用例总数" width="100" />
      <el-table-column prop="passed_cases" label="通过" width="80">
        <template #default="{ row }"><span style="color: #67c23a">{{ row.passed_cases }}</span></template>
      </el-table-column>
      <el-table-column prop="failed_cases" label="失败" width="80">
        <template #default="{ row }"><span style="color: #f56c6c">{{ row.failed_cases }}</span></template>
      </el-table-column>
      <el-table-column prop="blocked_cases" label="阻塞" width="80">
        <template #default="{ row }"><span style="color: #e6a23c">{{ row.blocked_cases }}</span></template>
      </el-table-column>
      <el-table-column prop="pass_rate" label="通过率" width="100">
        <template #default="{ row }">{{ row.pass_rate }}%</template>
      </el-table-column>
      <el-table-column prop="defect_count" label="缺陷数" width="80" />
      <el-table-column prop="generated_by_name" label="生成人" width="100" />
      <el-table-column prop="generated_at" label="生成时间" width="160">
        <template #default="{ row }">{{ formatDate(row.generated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="viewReport(row)">查看</el-button>
          <el-button size="small" type="success" @click="exportReport(row)">导出</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)" v-if="role === 'admin'">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="generateDialogVisible" title="生成测试报告" width="500px">
      <el-form :model="generateForm" label-width="100px">
        <el-form-item label="所属项目" required>
          <el-select v-model="generateForm.project_id" style="width: 100%" @change="onProjectChange">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="测试计划" required>
          <el-select v-model="generateForm.plan_id" style="width: 100%">
            <el-option v-for="pl in filteredPlans" :key="pl.id" :label="pl.version" :value="pl.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="测试阶段" required>
          <el-select v-model="generateForm.stage" style="width: 100%">
            <el-option label="SIT" value="SIT" />
            <el-option label="UAT" value="UAT" />
            <el-option label="PRE" value="PRE" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="generateDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleGenerate" :loading="generating">生成</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="viewDialogVisible" title="报告详情" width="800px" top="5vh">
      <div v-if="currentReport" class="report-detail">
        <h3>{{ currentReport.title }}</h3>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="测试阶段">{{ currentReport.stage }}</el-descriptions-item>
          <el-descriptions-item label="用例总数">{{ currentReport.total_cases }}</el-descriptions-item>
          <el-descriptions-item label="通过率">
            <span :style="{ color: currentReport.pass_rate >= 80 ? '#67c23a' : '#f56c6c' }">
              {{ currentReport.pass_rate }}%
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="通过">{{ currentReport.passed_cases }}</el-descriptions-item>
          <el-descriptions-item label="失败">{{ currentReport.failed_cases }}</el-descriptions-item>
          <el-descriptions-item label="阻塞">{{ currentReport.blocked_cases }}</el-descriptions-item>
          <el-descriptions-item label="未执行">{{ currentReport.unexecuted_cases }}</el-descriptions-item>
          <el-descriptions-item label="缺陷总数">{{ currentReport.defect_count }}</el-descriptions-item>
          <el-descriptions-item label="严重缺陷">{{ currentReport.critical_defects }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="reportData" class="report-section">
          <h4>执行明细</h4>
          <el-table :data="reportData.runs || []" stripe size="small" max-height="300">
            <el-table-column prop="testcase_id" label="用例ID" width="80" />
            <el-table-column prop="testcase_title" label="用例标题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.status === '通过' ? 'success' : row.status === '失败' ? 'danger' : 'warning'" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="150" show-overflow-tooltip />
          </el-table>
        </div>

        <div v-if="reportData && reportData.defects && reportData.defects.length > 0" class="report-section">
          <h4>关联缺陷</h4>
          <el-table :data="reportData.defects" stripe size="small" max-height="200">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="severity" label="严重程度" width="100" />
            <el-table-column prop="status" label="状态" width="100" />
          </el-table>
        </div>
      </div>
      <template #footer>
        <el-button @click="viewDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="exportReport(currentReport)" v-if="currentReport">导出Excel</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { reportApi, projectApi, planApi } from '../api'

const reports = ref([])
const projects = ref([])
const plans = ref([])
const loading = ref(false)
const generating = ref(false)
const generateDialogVisible = ref(false)
const viewDialogVisible = ref(false)
const currentReport = ref(null)
const reportData = ref(null)
const role = ref(localStorage.getItem('role') || 'member')

const filters = reactive({ project_id: null, plan_id: null })
const generateForm = reactive({ project_id: null, plan_id: null, stage: 'SIT' })

const filteredPlans = computed(() => {
  if (!generateForm.project_id) return plans.value
  return plans.value.filter(p => p.project_id === generateForm.project_id)
})

const formatDate = (d) => {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN')
}

const loadData = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.project_id) params.project_id = filters.project_id
    if (filters.plan_id) params.plan_id = filters.plan_id
    reports.value = await reportApi.list(params)
  } catch (e) { console.error(e) } finally { loading.value = false }
}

const loadProjects = async () => {
  try { projects.value = await projectApi.list() } catch (e) { console.error(e) }
}

const loadPlans = async () => {
  try { plans.value = await planApi.list({}) } catch (e) { console.error(e) }
}

const showGenerateDialog = () => {
  Object.assign(generateForm, { project_id: null, plan_id: null, stage: 'SIT' })
  generateDialogVisible.value = true
}

const onProjectChange = () => {
  generateForm.plan_id = null
}

const handleGenerate = async () => {
  if (!generateForm.project_id || !generateForm.plan_id) {
    ElMessage.warning('请选择项目和测试计划')
    return
  }
  generating.value = true
  try {
    await reportApi.generate(generateForm.plan_id, generateForm.stage)
    ElMessage.success('报告生成成功')
    generateDialogVisible.value = false
    loadData()
  } catch (e) { console.error(e) } finally { generating.value = false }
}

const viewReport = async (row) => {
  currentReport.value = row
  try {
    const detail = await reportApi.get(row.id)
    reportData.value = detail.summary ? JSON.parse(detail.summary) : null
  } catch (e) {
    reportData.value = null
  }
  viewDialogVisible.value = true
}

const exportReport = async (row) => {
  const token = localStorage.getItem('token')
  try {
    const response = await fetch(`/api/reports/${row.id}/export`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`导出失败: ${response.status} - ${errorText}`)
    }
    const blob = await response.blob()
    console.log('Blob size:', blob.size, 'type:', blob.type)
    if (blob.size === 0) {
      ElMessage.error('导出的文件为空，请检查报告数据')
      return
    }
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${row.id}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    console.error(e)
    ElMessage.error(e.message || '导出失败')
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除报告「${row.title}」?`, '提示', { type: 'warning' })
    await reportApi.remove(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}

onMounted(() => {
  loadData()
  loadProjects()
  loadPlans()
})
</script>

<style scoped>
.reports-page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.filter-bar { display: flex; gap: 10px; margin-bottom: 16px; }
.report-detail h3 { margin-top: 0; }
.report-section { margin-top: 20px; }
.report-section h4 { margin-bottom: 10px; color: #303133; }
</style>
