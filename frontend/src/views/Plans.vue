<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { planApi, projectApi, reportApi, p2Api, testcaseApi } from '../api'

const route = useRoute()
const router = useRouter()

const STAGES = ['SIT', 'UAT', 'PRE']
const stageTagType = (s) => ({ SIT: 'primary', UAT: 'warning', PRE: 'danger' }[s] || 'info')
const stageLabel = (s) => ({ SIT: 'SIT', UAT: 'UAT', PRE: '预发版' }[s] || s)

const projects = ref([])
const plans = ref([])
const loading = ref(false)
const createVisible = ref(false)
const formRef = ref()
const form = reactive({ project_id: '', version: '' })
const rules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
}

// 推进对话框
const advanceVisible = ref(false)
const advanceLoading = ref(false)
const advancePlan = ref(null)
const advanceProgress = ref(null)
const targetStage = ref('')

const query = reactive({ project_id: '' })

// 当前筛选的项目信息(用于显示横幅)
const currentProject = computed(() => {
  if (!query.project_id) return null
  const p = projects.value.find((x) => x.id === query.project_id)
  return p || null
})

async function loadProjects() {
  projects.value = await projectApi.list()
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (query.project_id) params.project_id = query.project_id
    plans.value = await planApi.list(params)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  if (!projects.value.length) {
    ElMessage.warning('请先到「测试项目」创建一个项目')
    return
  }
  form.project_id = query.project_id || ''
  form.version = ''
  createVisible.value = true
}

async function submitCreate() {
  await formRef.value.validate()
  await planApi.create({ project_id: form.project_id, version: form.version })
  ElMessage.success('计划已创建,当前阶段 SIT')
  createVisible.value = false
  load()
}

async function openAdvance(row) {
  advancePlan.value = row
  advanceVisible.value = true
  advanceLoading.value = true
  targetStage.value = ''
  try {
    advanceProgress.value = await planApi.progress(row.id)
  } finally {
    advanceLoading.value = false
  }
}

async function doAdvance() {
  const p = advanceProgress.value
  const nextStage = targetStage.value || getNextStage(p.current_stage)
  if (!nextStage) {
    ElMessage.error('没有可推进的下一阶段')
    return
  }
  await ElMessageBox.confirm(
    `确认将计划「${advancePlan.value.version}」从 ${stageLabel(p.current_stage)} 推进到 ${stageLabel(nextStage)}?`,
    '阶段推进',
    { type: 'warning' }
  )
  await planApi.advance(advancePlan.value.id, nextStage)
  ElMessage.success(`已推进到${stageLabel(nextStage)}阶段`)
  advanceVisible.value = false
  load()
}

function getNextStage(current) {
  const idx = STAGES.indexOf(current)
  return idx < STAGES.length - 1 ? STAGES[idx + 1] : null
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除计划「${row.version}」?其下所有执行记录将一并删除。`, '提示', {
    type: 'warning',
  })
  await planApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

async function exportReport(row) {
  const token = localStorage.getItem('token') || ''
  const resp = await fetch(reportApi.exportPlan(row.id), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok) {
    const msg = await resp.text()
    ElMessage.error('导出失败:' + (msg || resp.status))
    return
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `测试报告_${row.version}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('报告已导出')
}

function projName(pid) {
  const p = projects.value.find((x) => x.id === pid)
  return p ? p.name : pid
}

function openRounds(row) {
  router.push({
    name: 'testcases',
    query: { project_id: row.project_id, plan_id: row.id },
  })
}

// ---- 测试轮次管理 ----
const roundsVisible = ref(false)
const roundsPlan = ref(null)
const roundsList = ref([])
const roundsLoading = ref(false)
const createRoundVisible = ref(false)
const createRoundForm = reactive({ name: '' })

async function openRoundsDialog(row) {
  roundsPlan.value = row
  roundsVisible.value = true
  await loadRounds()
}

async function loadRounds() {
  if (!roundsPlan.value) return
  roundsLoading.value = true
  try {
    roundsList.value = await p2Api.listRounds(roundsPlan.value.id)
  } catch (e) {
    roundsList.value = []
  } finally {
    roundsLoading.value = false
  }
}

function openCreateRound() {
  createRoundForm.name = ''
  createRoundVisible.value = true
}

async function submitCreateRound() {
  if (!createRoundForm.name.trim()) {
    ElMessage.warning('请输入轮次名称')
    return
  }
  await p2Api.createRound({ plan_id: roundsPlan.value.id, name: createRoundForm.name })
  ElMessage.success('轮次已创建')
  createRoundVisible.value = false
  loadRounds()
}

async function completeRound(row) {
  await ElMessageBox.confirm(`确定将轮次「${row.name}」标记为已完成?`, '提示', { type: 'warning' })
  await p2Api.completeRound(row.id)
  ElMessage.success('轮次已完成')
  loadRounds()
}

// ---- 批量执行 ----
const batchVisible = ref(false)
const batchPlan = ref(null)
const batchRound = ref(null)
const batchStage = ref('SIT')
const batchItems = ref([])
const batchLoading = ref(false)
const batchSubmitting = ref(false)
const batchTestcases = ref([])
const batchTestcasesLoading = ref(false)

async function openBatchDialog(row) {
  batchPlan.value = row
  batchRound.value = null
  batchStage.value = row.current_stage || 'SIT'
  batchItems.value = []
  batchVisible.value = true
  await loadRoundsForBatch()
  await loadTestcasesForBatch()
}

async function loadRoundsForBatch() {
  if (!batchPlan.value) return
  try {
    roundsList.value = await p2Api.listRounds(batchPlan.value.id)
  } catch (e) {
    roundsList.value = []
  }
}

async function loadTestcasesForBatch() {
  if (!batchPlan.value) return
  batchTestcasesLoading.value = true
  try {
    const res = await testcaseApi.list({ project_id: batchPlan.value.project_id, page_size: 200 })
    batchTestcases.value = res.items || []
  } catch (e) {
    batchTestcases.value = []
  } finally {
    batchTestcasesLoading.value = false
  }
}

function toggleBatchItem(tc) {
  const idx = batchItems.value.findIndex(i => i.testcase_id === tc.id)
  if (idx >= 0) {
    batchItems.value.splice(idx, 1)
  } else {
    batchItems.value.push({ testcase_id: tc.id, status: '通过', remark: '' })
  }
}

function isBatchSelected(tcId) {
  return batchItems.value.some(i => i.testcase_id === tcId)
}

function setBatchStatus(tcId, status) {
  const item = batchItems.value.find(i => i.testcase_id === tcId)
  if (item) item.status = status
}

async function submitBatch() {
  if (!batchItems.value.length) {
    ElMessage.warning('请至少选择一个用例')
    return
  }
  batchSubmitting.value = true
  try {
    const res = await p2Api.batchExecute({
      plan_id: batchPlan.value.id,
      round_id: batchRound.value,
      stage: batchStage.value,
      items: batchItems.value,
    })
    ElMessage.success(`批量执行完成:成功 ${res.success} 条,失败 ${res.failed} 条`)
    batchVisible.value = false
    load()
  } catch (e) {
    // error handled by interceptor
  } finally {
    batchSubmitting.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  // 从URL query 接收项目信息,按编号+名称匹配
  const qPid = route.query.project_id
  const qNo = route.query.project_no
  const qName = route.query.project_name
  if (qPid) {
    query.project_id = Number(qPid)
  } else if (qNo || qName) {
    // 按编号或名称匹配项目
    const matched = projects.value.find((p) =>
      (qNo && p.project_no === String(qNo)) || (qName && p.name === String(qName))
    )
    if (matched) query.project_id = matched.id
  }
  load()
})

// ---- 阶段时间编辑 ----
const stageTimeVisible = ref(false)
const stageTimeForm = reactive({
  plan_id: null, sit_start: '', sit_end: '', uat_start: '', uat_end: '', pre_start: '', pre_end: '',
})

function openStageTimes(row) {
  stageTimeForm.plan_id = row.id
  stageTimeForm.sit_start = row.sit_start || ''
  stageTimeForm.sit_end = row.sit_end || ''
  stageTimeForm.uat_start = row.uat_start || ''
  stageTimeForm.uat_end = row.uat_end || ''
  stageTimeForm.pre_start = row.pre_start || ''
  stageTimeForm.pre_end = row.pre_end || ''
  stageTimeVisible.value = true
}

async function submitStageTimes() {
  await planApi.updateStageTimes(stageTimeForm.plan_id, { ...stageTimeForm })
  ElMessage.success('阶段时间已保存')
  stageTimeVisible.value = false
  load()
}
</script>

<template>
  <div>
    <div class="toolbar">
      <el-select v-model="query.project_id" placeholder="筛选项目" clearable filterable style="width: 280px" @change="load">
        <el-option v-for="p in projects" :key="p.id" :label="(p.project_no ? p.project_no + ' - ' : '') + p.name" :value="p.id" />
      </el-select>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>新建批次
      </el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <!-- 当前项目横幅 -->
    <el-alert
      v-if="currentProject"
      :title="`当前项目:${currentProject.project_no ? currentProject.project_no + ' - ' : ''}${currentProject.name}`"
      :description="`等级:${currentProject.level || '-'} | 类型:${currentProject.project_type || '-'} | 测试经理:${currentProject.test_manager || '-'} | 技术经理:${currentProject.tech_manager || '-'}`"
      type="info"
      :closable="true"
      show-icon
      style="margin-bottom: 12px"
      @close="query.project_id = ''; load()"
    />

    <el-table v-loading="loading" :data="plans" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="项目" width="160">
        <template #default="{ row }">{{ projName(row.project_id) }}</template>
      </el-table-column>
      <el-table-column prop="version" label="版本/轮次" width="140" />
      <el-table-column label="当前阶段" width="110">
        <template #default="{ row }">
          <el-tag :type="stageTagType(row.current_stage)" size="small">{{ stageLabel(row.current_stage) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === '已完成' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="SIT 进度" width="120">
        <template #default="{ row }">
          <span>{{ row.passed_cases }} / {{ row.total_cases }}</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="520" fixed="right">
        <template #default="{ row }">
          <el-button link type="success" @click="openRounds(row)">打开轮次</el-button>
          <el-button link type="primary" @click="openRoundsDialog(row)">轮次管理</el-button>
          <el-button link type="warning" @click="openBatchDialog(row)">批量执行</el-button>
          <el-button link type="primary" @click="openAdvance(row)" :disabled="row.status === '已完成'">阶段推进</el-button>
          <el-button link type="primary" @click="openStageTimes(row)">阶段时间</el-button>
          <el-button link type="success" @click="exportReport(row)">导出报告</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建计划 -->
    <el-dialog v-model="createVisible" title="新建测试计划" width="460px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="项目" prop="project_id">
          <el-select v-model="form.project_id" placeholder="选择项目" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="版本号" prop="version">
          <el-input v-model="form.version" placeholder="例如:v1.0、2026年第一轮" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 阶段推进 -->
    <el-dialog v-model="advanceVisible" :title="`阶段推进 - ${advancePlan?.version || ''}`" width="560px">
      <div v-loading="advanceLoading">
        <el-alert
          v-if="advanceProgress"
          :title="`当前阶段:${stageLabel(advanceProgress.current_stage)} | 计划状态:${advanceProgress.status}`"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        >
          <span>可灵活推进到任意后续阶段，无需当前阶段 100% 通过</span>
        </el-alert>

        <el-form v-if="advanceProgress" label-width="80px" style="margin-bottom: 16px">
          <el-form-item label="目标阶段">
            <el-select v-model="targetStage" placeholder="不选则推进到下一阶段" style="width: 100%">
              <el-option
                v-for="st in STAGES"
                :key="st"
                :label="stageLabel(st)"
                :value="st"
                :disabled="STAGES.indexOf(st) <= STAGES.indexOf(advanceProgress.current_stage)"
              />
            </el-select>
          </el-form-item>
        </el-form>

        <div v-if="advanceProgress" class="stages">
          <div v-for="st in STAGES" :key="st" class="stage-row">
            <div class="stage-name">
              <el-tag :type="stageTagType(st)" size="small">{{ stageLabel(st) }}</el-tag>
              <span v-if="advanceProgress.current_stage === st" class="cur">(当前)</span>
              <el-icon v-if="advanceProgress.stages[st].passed === advanceProgress.total && advanceProgress.total > 0" color="#67c23a" style="margin-left:6px"><CircleCheck /></el-icon>
            </div>
            <div class="stage-bar">
              <span>通过 {{ advanceProgress.stages[st].passed }} / 失败 {{ advanceProgress.stages[st].failed }} / 阻塞 {{ advanceProgress.stages[st].blocked }} / 未执行 {{ advanceProgress.stages[st].pending }} / 共 {{ advanceProgress.stages[st].total }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="advanceVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :disabled="!advanceProgress"
          @click="doAdvance"
        >确认推进</el-button>
      </template>
    </el-dialog>

    <!-- 阶段时间编辑 -->
    <el-dialog v-model="stageTimeVisible" title="编辑阶段时间" width="520px">
      <el-form label-width="120px">
        <el-divider content-position="left">SIT 阶段</el-divider>
        <el-form-item label="开始时间">
          <el-date-picker v-model="stageTimeForm.sit_start" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="选择时间" style="width:100%" />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker v-model="stageTimeForm.sit_end" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="选择时间" style="width:100%" />
        </el-form-item>
        <el-divider content-position="left">UAT 阶段</el-divider>
        <el-form-item label="开始时间">
          <el-date-picker v-model="stageTimeForm.uat_start" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="选择时间" style="width:100%" />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker v-model="stageTimeForm.uat_end" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="选择时间" style="width:100%" />
        </el-form-item>
        <el-divider content-position="left">预发版(PRE) 阶段</el-divider>
        <el-form-item label="开始时间">
          <el-date-picker v-model="stageTimeForm.pre_start" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="选择时间" style="width:100%" />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker v-model="stageTimeForm.pre_end" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="选择时间" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="stageTimeVisible = false">取消</el-button>
        <el-button type="primary" @click="submitStageTimes">保存</el-button>
      </template>
    </el-dialog>

    <!-- 轮次管理对话框 -->
    <el-dialog v-model="roundsVisible" :title="`轮次管理 - ${roundsPlan?.version || ''}`" width="680px">
      <div class="toolbar" style="margin-bottom: 12px">
        <el-button type="primary" size="small" @click="openCreateRound">
          <el-icon><Plus /></el-icon>新建轮次
        </el-button>
        <el-button size="small" @click="loadRounds">刷新</el-button>
      </div>
      <el-table v-loading="roundsLoading" :data="roundsList" border size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="轮次名称" min-width="120" />
        <el-table-column prop="round_number" label="轮次号" width="80" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === '已完成' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="120">
          <template #default="{ row }">
            <span>{{ row.passed_cases }}/{{ row.total_cases }} 通过</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button v-if="row.status !== '已完成'" link type="success" size="small" @click="completeRound(row)">完成</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!roundsLoading && !roundsList.length" description="暂无轮次" :image-size="60" />
    </el-dialog>

    <!-- 新建轮次对话框 -->
    <el-dialog v-model="createRoundVisible" title="新建轮次" width="420px">
      <el-form label-width="80px">
        <el-form-item label="轮次名称" required>
          <el-input v-model="createRoundForm.name" placeholder="例如:第一轮回归测试" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createRoundVisible = false">取消</el-button>
        <el-button type="primary" @click="submitCreateRound">创建</el-button>
      </template>
    </el-dialog>

    <!-- 批量执行对话框 -->
    <el-dialog v-model="batchVisible" :title="`批量执行 - ${batchPlan?.version || ''}`" width="800px" top="5vh">
      <el-form :inline="true" style="margin-bottom: 12px">
        <el-form-item label="轮次">
          <el-select v-model="batchRound" placeholder="选择轮次(可选)" clearable style="width: 200px">
            <el-option v-for="r in roundsList" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="batchStage" style="width: 120px">
            <el-option v-for="s in STAGES" :key="s" :label="stageLabel(s)" :value="s" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-alert :title="`已选择 ${batchItems.length} 个用例`" type="info" :closable="false" show-icon style="margin-bottom: 12px" />

      <el-table v-loading="batchTestcasesLoading" :data="batchTestcases" border size="small" max-height="400">
        <el-table-column label="选择" width="60">
          <template #default="{ row }">
            <el-checkbox :model-value="isBatchSelected(row.id)" @change="toggleBatchItem(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="结果" width="140">
          <template #default="{ row }">
            <el-radio-group v-if="isBatchSelected(row.id)" :model-value="(() => { const item = batchItems.find(i => i.testcase_id === row.id); return item ? item.status : '通过' })()" @update:model-value="setBatchStatus(row.id, $event)" size="small">
              <el-radio-button value="通过">通过</el-radio-button>
              <el-radio-button value="失败">失败</el-radio-button>
              <el-radio-button value="阻塞">阻塞</el-radio-button>
            </el-radio-group>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="batchVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSubmitting" :disabled="!batchItems.length" @click="submitBatch">执行 {{ batchItems.length }} 条用例</el-button>
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
.stages {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.stage-row {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
}
.stage-name {
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
}
.stage-name .cur {
  margin-left: 6px;
  color: #409eff;
  font-size: 12px;
}
.stage-bar {
  color: #606266;
  font-size: 13px;
}
</style>
