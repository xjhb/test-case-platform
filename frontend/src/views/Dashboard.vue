<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart, LineChart, GaugeChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { statsApi, projectApi, planApi } from '../api'
import { useAuthStore } from '../stores/auth'

use([CanvasRenderer, PieChart, BarChart, LineChart, GaugeChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent])

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')

const loading = ref(false)
const data = ref(null)

const STAGE_LABELS = { SIT: 'SIT', UAT: 'UAT', PRE: '预发版' }
const STAGES = ['SIT', 'UAT', 'PRE']

const projects = ref([])
const plans = ref([])
const filters = reactive({ project_id: '', plan_id: '', stage: '' })

// 图表 refs
const gaugeRef = ref(null)
const pieRef = ref(null)
const stageBarRef = ref(null)
const trendRef = ref(null)
const personRef = ref(null)
const passRateTrendRef = ref(null)
const defectConvergenceRef = ref(null)
const workloadDistRef = ref(null)

// 新增图表数据
const passRateTrends = ref([])
const defectConvergence = ref([])
const workloadDistribution = ref([])

const healthColor = (level) => ({ red: '#f56c6c', yellow: '#e6a23c', green: '#67c23a' }[level] || '#909399')
const healthBg = (level) => ({ red: '#fef0f0', yellow: '#fdf6ec', green: '#f0f9eb' }[level] || '#f4f4f5')
const healthBorder = (level) => ({ red: '#f56c6c', yellow: '#e6a23c', green: '#67c23a' }[level] || '#909399')

const gaugeOption = computed(() => {
  const score = data.value?.quality?.health_score || 0
  const level = data.value?.quality?.health_level || 'green'
  return {
    series: [
      {
        type: 'gauge',
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max: 100,
        progress: { show: true, width: 14, itemStyle: { color: healthColor(level) } },
        axisLine: { lineStyle: { width: 14, color: [[1, '#f0f0f0']] } },
        pointer: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false },
        detail: {
          valueAnimation: true,
          formatter: '{value}%',
          fontSize: 28,
          fontWeight: 'bold',
          color: healthColor(level),
          offsetCenter: [0, '20%'],
        },
        title: {
          show: true,
          offsetCenter: [0, '55%'],
          fontSize: 14,
          color: '#909399',
        },
        data: [{ value: score, name: '质量健康度' }],
      },
    ],
  }
})

const pieOption = computed(() => {
  const stages = data.value?.quality?.stages || []
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
    legend: { bottom: 0, data: stages.map((s) => STAGE_LABELS[s.stage]) },
    series: [
      {
        type: 'pie',
        radius: ['35%', '60%'],
        center: ['50%', '42%'],
        data: stages.map((s) => ({ name: STAGE_LABELS[s.stage], value: s.pass_rate })),
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{c}%' },
        color: ['#409eff', '#e6a23c', '#f56c6c'],
      },
    ],
  }
})

const stageBarOption = computed(() => {
  const stages = data.value?.efficiency?.stage_completion || []
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: '{b}: {c}%' },
    grid: { left: '3%', right: '8%', bottom: '15%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: stages.map((s) => STAGE_LABELS[s.stage]), axisLabel: { fontSize: 12 } },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        type: 'bar',
        data: stages.map((s) => ({
          value: s.rate,
          itemStyle: {
            color: s.rate >= 90 ? '#67c23a' : s.rate >= 70 ? '#e6a23c' : '#f56c6c',
            borderRadius: [4, 4, 0, 0],
          },
        })),
        barWidth: '40%',
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 11 },
      },
    ],
  }
})

const trendOption = computed(() => {
  const trend = data.value?.efficiency?.daily_trend || []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '8%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: trend.map((t) => t.date), boundaryGap: false },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'line',
        data: trend.map((t) => t.count),
        smooth: true,
        areaStyle: { opacity: 0.15 },
        itemStyle: { color: '#409eff' },
        lineStyle: { width: 2 },
      },
    ],
  }
})

const personOption = computed(() => {
  const persons = data.value?.efficiency?.per_person || []
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '8%', containLabel: true },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: persons.map((p) => p.name), inverse: true },
    series: [
      {
        type: 'bar',
        data: persons.map((p) => p.count),
        barWidth: '50%',
        itemStyle: { color: '#67c23a', borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right' },
      },
    ],
  }
})

const passRateTrendOption = computed(() => {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: passRateTrends.value.map((t) => t.version), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      {
        type: 'line',
        data: passRateTrends.value.map((t) => t.pass_rate),
        smooth: true,
        areaStyle: { opacity: 0.2 },
        itemStyle: { color: '#409eff' },
        lineStyle: { width: 3 },
        markLine: {
          data: [{ yAxis: 90, label: { formatter: '目标: 90%' }, lineStyle: { color: '#67c23a', type: 'dashed' } }],
        },
      },
    ],
  }
})

const defectConvergenceOption = computed(() => {
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['累计缺陷', '新增', '关闭'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: defectConvergence.value.map((d) => d.date), boundaryGap: false },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        name: '累计缺陷',
        type: 'line',
        data: defectConvergence.value.map((d) => d.cumulative),
        smooth: true,
        itemStyle: { color: '#f56c6c' },
        areaStyle: { opacity: 0.1 },
      },
      {
        name: '新增',
        type: 'bar',
        data: defectConvergence.value.map((d) => d.new),
        itemStyle: { color: '#e6a23c' },
      },
      {
        name: '关闭',
        type: 'bar',
        data: defectConvergence.value.map((d) => d.resolved),
        itemStyle: { color: '#67c23a' },
      },
    ],
  }
})

const workloadDistOption = computed(() => {
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['通过', '失败', '阻塞'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '8%', containLabel: true },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: workloadDistribution.value.map((w) => w.name), inverse: true },
    series: [
      {
        name: '通过',
        type: 'bar',
        stack: 'total',
        data: workloadDistribution.value.map((w) => w.passed),
        itemStyle: { color: '#67c23a' },
      },
      {
        name: '失败',
        type: 'bar',
        stack: 'total',
        data: workloadDistribution.value.map((w) => w.failed),
        itemStyle: { color: '#f56c6c' },
      },
      {
        name: '阻塞',
        type: 'bar',
        stack: 'total',
        data: workloadDistribution.value.map((w) => w.blocked),
        itemStyle: { color: '#e6a23c' },
      },
    ],
  }
})

async function loadProjects() {
  projects.value = await projectApi.list()
}

async function loadPlans() {
  if (!filters.project_id) {
    plans.value = []
    filters.plan_id = ''
    return
  }
  plans.value = await planApi.list({ project_id: filters.project_id })
  if (plans.value.length) {
    filters.plan_id = plans.value[0].id
    filters.stage = plans.value[0].current_stage
  } else {
    filters.plan_id = ''
    filters.stage = ''
  }
}

async function onProjectChange() {
  filters.plan_id = ''
  filters.stage = ''
  await loadPlans()
  load()
}

function onPlanChange() {
  const p = plans.value.find((x) => x.id === filters.plan_id)
  filters.stage = p ? p.current_stage : ''
  load()
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.project_id) params.project_id = filters.project_id
    if (filters.plan_id) params.plan_id = filters.plan_id
    if (filters.stage) params.stage = filters.stage
    data.value = await statsApi.dashboard(params)

    // 加载新增的趋势数据
    if (filters.project_id) {
      try {
        const [trends, convergence, workload] = await Promise.all([
          statsApi.passRateTrends({ project_id: filters.project_id, stage: filters.stage || 'SIT' }),
          statsApi.defectConvergence({ project_id: filters.project_id, plan_id: filters.plan_id }),
          statsApi.workloadDistribution({ project_id: filters.project_id, plan_id: filters.plan_id, days: 30 }),
        ])
        passRateTrends.value = trends.trends || []
        defectConvergence.value = convergence.convergence || []
        workloadDistribution.value = workload.distribution || []
      } catch (e) {
        console.error('加载趋势数据失败:', e)
      }
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  if (projects.value.length) {
    filters.project_id = projects.value[0].id
    await loadPlans()
  }
  load()
})

onBeforeUnmount(() => {
  gaugeRef.value?.dispose()
  pieRef.value?.dispose()
  stageBarRef.value?.dispose()
  trendRef.value?.dispose()
  personRef.value?.dispose()
  passRateTrendRef.value?.dispose()
  defectConvergenceRef.value?.dispose()
  workloadDistRef.value?.dispose()
})
</script>

<template>
  <div v-loading="loading">
    <!-- 筛选栏(右上角) -->
    <div class="filter-bar">
      <el-select v-model="filters.project_id" placeholder="所属项目" clearable style="width: 180px" @change="onProjectChange">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="filters.plan_id" placeholder="项目批次" clearable style="width: 180px" :disabled="!filters.project_id" @change="onPlanChange">
        <el-option v-for="p in plans" :key="p.id" :label="p.version" :value="p.id" />
      </el-select>
    </div>

    <!-- 区块一:概览 -->
    <div class="section-title"><el-icon><DataLine /></el-icon> 概览</div>
    <div class="cards">
      <el-card shadow="hover" class="num-card">
        <div class="num" style="color: #409eff">{{ data?.overview?.projects || 0 }}</div>
        <div class="label">项目数</div>
      </el-card>
      <el-card shadow="hover" class="num-card">
        <div class="num" style="color: #67c23a">{{ data?.overview?.cases || 0 }}</div>
        <div class="label">测试用例</div>
      </el-card>
      <el-card shadow="hover" class="num-card">
        <div class="num" style="color: #e6a23c">{{ data?.overview?.plans || 0 }}</div>
        <div class="label">测试批次</div>
      </el-card>
      <el-card shadow="hover" class="num-card">
        <div class="num" style="color: #f56c6c">{{ data?.overview?.plans_in_progress || 0 }}</div>
        <div class="label">进行中批次</div>
      </el-card>
    </div>

    <!-- 区块二:测试质量 -->
    <div class="section-title"><el-icon><Checked /></el-icon> 测试质量</div>
    <div class="quality-row">
      <!-- 健康度仪表盘 -->
      <el-card shadow="hover" class="quality-gauge">
        <template #header><span>质量健康度</span></template>
        <div class="health-wrap" :style="{ background: healthBg(data?.quality?.health_level) }">
          <v-chart ref="gaugeRef" :option="gaugeOption" autoresize style="height: 200px" />
          <div class="health-tag" :style="{ color: healthColor(data?.quality?.health_level) }">
            <el-tag :type="data?.quality?.health_level === 'green' ? 'success' : data?.quality?.health_level === 'yellow' ? 'warning' : 'danger'" size="large">
              {{ data?.quality?.health_desc || '无数据' }}
            </el-tag>
          </div>
        </div>
      </el-card>

      <!-- 三阶段质量 -->
      <el-card shadow="hover" class="quality-stages">
        <template #header><span>各阶段质量指标</span></template>
        <div v-if="data?.quality?.stages?.length" class="stage-cards">
          <div v-for="s in data.quality.stages" :key="s.stage" class="stage-card"
               :style="{ borderLeft: `4px solid ${healthColor(s.health_level)}` }">
            <div class="stage-name">{{ STAGE_LABELS[s.stage] }}</div>
            <div class="stage-rate" :style="{ color: healthColor(s.health_level) }">{{ s.pass_rate }}%</div>
            <div class="stage-detail">
              通过 {{ s.passed }} / 失败 {{ s.failed }} / 阻塞 {{ s.blocked }} / 未执行 {{ s.pending }}
            </div>
            <el-tag :type="s.health_level === 'green' ? 'success' : s.health_level === 'yellow' ? 'warning' : 'danger'" size="small">
              {{ s.health_desc }}
            </el-tag>
          </div>
        </div>
        <el-empty v-else description="请选择项目批次" :image-size="60" />
      </el-card>

      <!-- 严重缺陷 -->
      <el-card shadow="hover" class="quality-severe">
        <template #header><span>严重缺陷预警</span></template>
        <div v-if="data?.quality" class="severe-wrap">
          <div class="severe-num" :style="{ color: data.quality.severe_defect_ratio >= 50 ? '#f56c6c' : data.quality.severe_defect_ratio >= 30 ? '#e6a23c' : '#67c23a' }">
            {{ data.quality.severe_defect_ratio }}%
          </div>
          <div class="severe-label">P0用例失败占比</div>
          <el-divider />
          <div class="severe-rule">
            <div><span class="dot red"></span> ≥50% 严重警告</div>
            <div><span class="dot yellow"></span> 30-50% 需关注</div>
            <div><span class="dot green"></span> &lt;30% 健康</div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 质量饼图 -->
    <el-card shadow="hover" v-if="data?.quality?.stages?.length" style="margin-top: 12px">
      <template #header><span>各阶段通过率分布</span></template>
      <v-chart ref="pieRef" :option="pieOption" autoresize style="height: 280px" />
    </el-card>

    <!-- 区块三:测试效率 -->
    <div class="section-title"><el-icon><TrendCharts /></el-icon> 测试效率(测试进度)</div>
    <div class="efficiency-row">
      <!-- 执行进度 -->
      <el-card shadow="hover" class="eff-card">
        <template #header><span>执行进度</span></template>
        <div class="progress-wrap">
          <el-progress
            type="dashboard"
            :percentage="data?.efficiency?.execution_progress || 0"
            :color="data?.efficiency?.execution_progress >= 90 ? '#67c23a' : data?.efficiency?.execution_progress >= 70 ? '#e6a23c' : '#f56c6c'"
            :width="120"
          />
          <div class="progress-label">{{ data?.efficiency?.execution_progress || 0 }}% 已执行</div>
        </div>
      </el-card>

      <!-- 阶段完成度 -->
      <el-card shadow="hover" class="eff-card">
        <template #header><span>阶段完成度</span></template>
        <v-chart v-if="data?.efficiency?.stage_completion?.length" ref="stageBarRef" :option="stageBarOption" autoresize style="height: 220px" />
        <el-empty v-else description="暂无数据" :image-size="60" />
      </el-card>
    </div>

    <div class="efficiency-row" style="margin-top: 12px">
      <!-- 每日趋势 -->
      <el-card shadow="hover" class="eff-card">
        <template #header><span>每日执行趋势(近7天)</span></template>
        <v-chart v-if="data?.efficiency?.daily_trend?.length" ref="trendRef" :option="trendOption" autoresize style="height: 240px" />
        <el-empty v-else description="暂无数据" :image-size="60" />
      </el-card>

      <!-- 人均执行量 -->
      <el-card shadow="hover" class="eff-card">
        <template #header><span>人均执行量</span></template>
        <v-chart v-if="data?.efficiency?.per_person?.length" ref="personRef" :option="personOption" autoresize style="height: 240px" />
        <el-empty v-else description="暂无数据" :image-size="60" />
      </el-card>
    </div>

    <!-- 区块四:趋势分析 -->
    <div class="section-title"><el-icon><TrendCharts /></el-icon> 趋势分析</div>
    <div class="efficiency-row">
      <!-- 版本通过率趋势 -->
      <el-card shadow="hover" class="eff-card">
        <template #header><span>版本通过率趋势</span></template>
        <v-chart v-if="passRateTrends.length" ref="passRateTrendRef" :option="passRateTrendOption" autoresize style="height: 280px" />
        <el-empty v-else description="暂无数据" :image-size="60" />
      </el-card>

      <!-- 缺陷收敛曲线 -->
      <el-card shadow="hover" class="eff-card">
        <template #header><span>缺陷收敛曲线</span></template>
        <v-chart v-if="defectConvergence.length" ref="defectConvergenceRef" :option="defectConvergenceOption" autoresize style="height: 280px" />
        <el-empty v-else description="暂无数据" :image-size="60" />
      </el-card>
    </div>

    <div class="efficiency-row" style="margin-top: 12px">
      <!-- 人员工作量分布 -->
      <el-card shadow="hover" style="flex: 1">
        <template #header><span>人员工作量分布(近30天)</span></template>
        <v-chart v-if="workloadDistribution.length" ref="workloadDistRef" :option="workloadDistOption" autoresize style="height: 300px" />
        <el-empty v-else description="暂无数据" :image-size="60" />
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.filter-bar {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-bottom: 16px;
}
.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #303133;
  margin: 20px 0 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.section-title .el-icon {
  color: #409eff;
}
.cards {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
}
.num-card {
  flex: 1;
  text-align: center;
}
.num {
  font-size: 32px;
  font-weight: bold;
}
.label {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
/* 测试质量 */
.quality-row {
  display: flex;
  gap: 12px;
}
.quality-gauge {
  flex: 0 0 280px;
}
.quality-stages {
  flex: 1;
}
.quality-severe {
  flex: 0 0 240px;
}
.health-wrap {
  border-radius: 8px;
  padding: 8px;
  text-align: center;
}
.health-tag {
  margin-top: 4px;
}
.stage-cards {
  display: flex;
  gap: 10px;
}
.stage-card {
  flex: 1;
  padding: 12px;
  border-radius: 6px;
  background: #fafafa;
  text-align: center;
}
.stage-name {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 4px;
}
.stage-rate {
  font-size: 24px;
  font-weight: bold;
  margin-bottom: 4px;
}
.stage-detail {
  font-size: 11px;
  color: #909399;
  margin-bottom: 6px;
}
.severe-wrap {
  text-align: center;
}
.severe-num {
  font-size: 36px;
  font-weight: bold;
}
.severe-label {
  color: #909399;
  font-size: 12px;
}
.severe-rule {
  font-size: 12px;
  color: #606266;
  text-align: left;
}
.severe-rule div {
  margin: 4px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot.red { background: #f56c6c; }
.dot.yellow { background: #e6a23c; }
.dot.green { background: #67c23a; }
/* 测试效率 */
.efficiency-row {
  display: flex;
  gap: 12px;
}
.eff-card {
  flex: 1;
}
.progress-wrap {
  text-align: center;
  padding: 20px 0;
}
.progress-label {
  margin-top: 8px;
  color: #909399;
  font-size: 13px;
}
</style>
