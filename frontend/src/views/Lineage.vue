<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { lineageApi, projectApi } from '../api'

use([CanvasRenderer, GraphChart, TooltipComponent, LegendComponent])

const router = useRouter()

const TYPES = [
  { value: 'requirement', label: '需求' },
  { value: 'testcase', label: '用例' },
  { value: 'plan', label: '批次' },
  { value: 'run', label: '执行记录' },
  { value: 'defect', label: '缺陷' },
  { value: 'environment', label: '环境' },
]
// 影响分析只支持这五类对象为根(执行记录本身不可改删)
const IMPACT_TYPES = ['requirement', 'testcase', 'plan', 'defect', 'environment']
const COLOR = {
  requirement: '#8e44ad', testcase: '#409eff', plan: '#e6a23c',
  run: '#909399', defect: '#f56c6c', environment: '#67c23a',
}
const COLOR_BY_LABEL = {
  需求: COLOR.requirement, 用例: COLOR.testcase, 批次: COLOR.plan,
  执行记录: COLOR.run, 缺陷: COLOR.defect, 环境: COLOR.environment,
}
const SIZE = {
  requirement: 46, testcase: 34, plan: 42, run: 18, defect: 30, environment: 26,
}
const LEVEL_TAG = { danger: 'danger', warning: 'warning', info: 'info' }
const RISK_TAG = { high: 'error', medium: 'warning', low: 'success' }

const projects = ref([])
const roots = ref([])
const rootsLoading = ref(false)
const loading = ref(false)
const graph = ref({ nodes: [], links: [], categories: [], counts: {}, truncated: false })
const overview = ref(null)

const query = reactive({
  project_id: null,
  root_type: 'testcase',
  root_id: null,
  depth: 2,
  max_nodes: 300,
})

const impactVisible = ref(false)
const impactLoading = ref(false)
const impact = ref(null)
const impactTarget = reactive({ type: '', id: 0, name: '' })
const change = ref('modify')

async function loadProjects() {
  projects.value = await projectApi.list()
  if (!query.project_id && projects.value.length) {
    query.project_id = projects.value[0].id
  }
}

async function loadRoots(keyword = '') {
  if (!query.project_id) return
  rootsLoading.value = true
  try {
    const params = { project_id: query.project_id, type: query.root_type, limit: 200 }
    if (keyword) params.keyword = keyword
    const res = await lineageApi.roots(params)
    roots.value = res.items
  } finally {
    rootsLoading.value = false
  }
}

async function loadOverview() {
  if (!query.project_id) return
  overview.value = await lineageApi.overview(query.project_id)
}

async function load() {
  if (!query.project_id) return
  loading.value = true
  try {
    const params = {
      project_id: query.project_id,
      depth: query.depth,
      max_nodes: query.max_nodes,
    }
    if (query.root_id) {
      params.root_type = query.root_type
      params.root_id = query.root_id
    }
    graph.value = await lineageApi.graph(params)
  } finally {
    loading.value = false
  }
}

async function reload() {
  await Promise.all([load(), loadOverview()])
}

function onProjectChange() {
  query.root_id = null
  roots.value = []
  loadRoots()
  reload()
}

function onTypeChange() {
  query.root_id = null
  loadRoots()
  load()
}

function clearRoot() {
  query.root_id = null
  load()
}

// 起点的影响分析不必非得去图里点节点,给一个直达入口
function openRootImpact() {
  if (!query.root_id || !IMPACT_TYPES.includes(query.root_type)) {
    ElMessage.info('请先选择一个起点(执行记录不支持影响分析)')
    return
  }
  const hit = roots.value.find((r) => r.id === query.root_id)
  impactTarget.type = query.root_type
  impactTarget.id = query.root_id
  impactTarget.name = hit?.name || `#${query.root_id}`
  change.value = 'modify'
  impactVisible.value = true
  loadImpact()
}

const shortName = (s, n = 18) => (s && s.length > n ? `${s.slice(0, n)}…` : s || '')

const option = computed(() => {
  const nodes = graph.value.nodes || []
  const rootId = graph.value.root
  return {
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'edge') return `${p.data.source} → ${p.data.target}<br/>关系: ${p.data.name}`
        const d = p.data
        const info = Object.entries(d.info || {}).map(([k, v]) => `${k}: ${v}`).join('<br/>')
        return `<b>[${d.typeLabel}]</b> ${d.rawName}<br/>${info}<br/><span style="color:#909399">点击查看影响分析</span>`
      },
    },
    legend: [{ data: (graph.value.categories || []).map((c) => c.name), top: 4 }],
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        categories: (graph.value.categories || []).map((c) => ({
          name: c.name,
          itemStyle: { color: COLOR_BY_LABEL[c.name] || '#909399' },
        })),
        data: nodes.map((n) => ({
          id: n.id,
          name: shortName(n.name),
          rawName: n.name,
          typeLabel: n.type_label,
          info: n.info,
          raw: n,
          category: n.category,
          symbolSize: n.id === rootId ? SIZE[n.type] + 18 : SIZE[n.type],
          itemStyle: n.id === rootId ? { borderColor: '#303133', borderWidth: 3 } : undefined,
          label: { show: n.type !== 'run' || nodes.length <= 40 },
        })),
        links: (graph.value.links || []).map((l) => ({
          source: l.source,
          target: l.target,
          name: l.type,
          label: {
            show: nodes.length <= 60,
            formatter: l.type,
            fontSize: 10,
            color: '#909399',
          },
        })),
        force: { repulsion: 260, edgeLength: [70, 150], gravity: 0.08, friction: 0.2 },
        label: { show: true, position: 'right', fontSize: 11 },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: 8,
        lineStyle: { color: '#c0c4cc', width: 1.4, curveness: 0.08, opacity: 0.85 },
        emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
      },
    ],
  }
})

function onChartClick(p) {
  if (p.dataType !== 'node' || !p.data?.raw) return
  const n = p.data.raw
  if (!IMPACT_TYPES.includes(n.type)) {
    ElMessage.info('执行记录本身不可修改或删除,请在用例或批次的影响分析里查看它')
    return
  }
  impactTarget.type = n.type
  impactTarget.id = Number(n.id.split(':')[1])
  impactTarget.name = n.name
  change.value = 'modify'
  impactVisible.value = true
  loadImpact()
}

async function loadImpact() {
  if (!impactTarget.id) return
  impactLoading.value = true
  try {
    impact.value = await lineageApi.impact({
      project_id: query.project_id,
      type: impactTarget.type,
      id: impactTarget.id,
      change: change.value,
    })
  } finally {
    impactLoading.value = false
  }
}

function go(link) {
  if (!link) return
  impactVisible.value = false
  router.push(link)
}

const countsText = computed(() => {
  const c = graph.value.counts || {}
  return TYPES.filter((t) => c[t.value]).map((t) => `${t.label} ${c[t.value]}`).join(' · ')
})

onMounted(async () => {
  await loadProjects()
  await loadRoots()
  await reload()
})
</script>

<template>
  <div>
    <div class="filter">
      <el-select v-model="query.project_id" placeholder="选择项目" style="width: 220px" @change="onProjectChange">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="query.root_type" style="width: 120px" @change="onTypeChange">
        <el-option v-for="t in TYPES" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-select
        v-model="query.root_id"
        placeholder="选择起点(不选则为全景图)"
        filterable
        remote
        clearable
        :remote-method="loadRoots"
        :loading="rootsLoading"
        style="width: 300px"
        @change="load"
      >
        <el-option v-for="r in roots" :key="r.id" :label="r.name" :value="r.id">
          <span>{{ r.name }}</span>
          <span class="opt-note">{{ r.note }}</span>
        </el-option>
      </el-select>
      <el-select v-model="query.depth" style="width: 110px" @change="load">
        <el-option v-for="d in [1, 2, 3, 4]" :key="d" :label="`展开 ${d} 层`" :value="d" />
      </el-select>
      <el-select v-model="query.max_nodes" style="width: 130px" @change="load">
        <el-option v-for="m in [50, 100, 300, 800]" :key="m" :label="`最多 ${m} 节点`" :value="m" />
      </el-select>
      <el-button type="primary" @click="reload">刷新</el-button>
      <el-button v-if="query.root_id" type="warning" plain @click="openRootImpact">影响分析</el-button>
      <el-button v-if="query.root_id" @click="clearRoot">回到全景图</el-button>
    </div>

    <el-alert
      v-if="overview?.gaps?.length"
      class="gaps"
      :closable="false"
      type="info"
      show-icon
      :title="`血缘体检: ${overview.gaps.length === 1 && overview.gaps[0].level === 'success' ? '追溯关系完整' : `${overview.gaps.length} 项待处理`}`"
    >
      <div v-for="(g, i) in overview.gaps" :key="i" class="gap-line">
        <el-tag :type="g.level === 'success' ? 'success' : (g.level === 'warning' ? 'warning' : 'info')" size="small">
          {{ g.level === 'success' ? '正常' : (g.level === 'warning' ? '断链' : '提示') }}
        </el-tag>
        <span>{{ g.text }}</span>
      </div>
      <div v-if="overview.coverage" class="gap-line coverage">
        需求覆盖率 {{ overview.coverage.requirement_coverage }}% ·
        用例关联需求率 {{ overview.coverage.testcase_link_rate }}% ·
        孤儿缺陷 {{ overview.coverage.orphan_defects }} 个
      </div>
    </el-alert>

    <el-card v-loading="loading" shadow="never">
      <template #header>
        <div class="card-head">
          <span>数据血缘图</span>
          <span class="sub">
            {{ countsText || '暂无数据' }}
            <el-tag v-if="graph.truncated" type="warning" size="small">已截断到 {{ query.max_nodes }} 个节点</el-tag>
          </span>
        </div>
      </template>
      <el-empty v-if="!graph.nodes?.length" description="该项目还没有可追溯的关联数据" />
      <v-chart v-else :option="option" autoresize style="height: 620px" @click="onChartClick" />
      <div class="tip">
        箭头方向为业务流向: 需求 → 用例 → 执行记录 → 缺陷。图上只画已落库的显式关联;
        未圈选范围的批次按项目全部用例隐式覆盖,这类关系只在影响分析里提示。点击任意节点查看影响分析。
      </div>
    </el-card>

    <el-drawer v-model="impactVisible" size="680px" :title="`影响分析: ${impactTarget.name}`">
      <div v-loading="impactLoading">
        <template v-if="impact">
          <div class="impact-head">
            <el-radio-group v-model="change" size="small" @change="loadImpact">
              <el-radio-button value="modify">如果修改它</el-radio-button>
              <el-radio-button value="delete">如果删除它</el-radio-button>
            </el-radio-group>
            <el-tag :type="RISK_TAG[impact.risk.level]" effect="dark">
              风险{{ impact.risk.label }}
            </el-tag>
            <span class="risk-reason">{{ impact.risk.reason }}</span>
          </div>

          <div class="summary">
            <div v-for="s in impact.summary" :key="s.label" class="sum-item">
              <div class="sum-value">{{ s.value }}</div>
              <div class="sum-label">{{ s.label }}</div>
            </div>
          </div>

          <el-alert type="info" :closable="false" class="suggest" title="处置建议">
            <ol class="suggest-list">
              <li v-for="(s, i) in impact.suggestion" :key="i">{{ s }}</li>
            </ol>
          </el-alert>

          <div v-for="sec in impact.sections" :key="sec.key" class="section">
            <div class="sec-head">
              <el-tag :type="LEVEL_TAG[sec.level]" size="small" effect="plain">{{ sec.title }}</el-tag>
              <span class="sec-count">{{ sec.count }} 项</span>
              <span class="sec-note">{{ sec.note }}</span>
            </div>
            <el-table v-if="sec.items.length" :data="sec.items" size="small" border>
              <el-table-column prop="name" label="对象" min-width="200" show-overflow-tooltip />
              <el-table-column prop="note" label="状态" width="180" show-overflow-tooltip />
              <el-table-column label="" width="70" align="center">
                <template #default="{ row }">
                  <el-button v-if="row.link" link type="primary" size="small" @click="go(row.link)">查看</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="sec-empty">无</div>
            <div class="sec-action">{{ sec.action }}</div>
          </div>

          <div class="crit-note">
            「计入紧急」的严重程度由数据字典决定,当前为: {{ (impact.critical_severities || []).join('、') || '未配置' }}
          </div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.filter {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
  align-items: center;
}
.opt-note {
  float: right;
  color: #909399;
  font-size: 12px;
}
.gaps {
  margin-bottom: 12px;
}
.gap-line {
  display: flex;
  gap: 8px;
  align-items: center;
  line-height: 22px;
}
.gap-line.coverage {
  color: #606266;
  font-size: 12px;
  margin-top: 4px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-head .sub {
  color: #909399;
  font-size: 13px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.tip {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
  line-height: 20px;
}
.impact-head {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.risk-reason {
  color: #606266;
  font-size: 13px;
}
.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}
.sum-item {
  flex: 1 1 88px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 6px;
  text-align: center;
}
.sum-value {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.sum-label {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.suggest {
  margin-bottom: 14px;
}
.suggest-list {
  margin: 0;
  padding-left: 18px;
}
.suggest-list li {
  line-height: 22px;
  font-size: 13px;
}
.section {
  border-top: 1px solid #ebeef5;
  padding: 12px 0;
}
.sec-head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.sec-count {
  color: #303133;
  font-size: 13px;
  font-weight: 600;
}
.sec-note {
  color: #909399;
  font-size: 12px;
}
.sec-empty {
  color: #c0c4cc;
  font-size: 13px;
  padding: 6px 0;
}
.sec-action {
  margin-top: 6px;
  color: #606266;
  font-size: 12px;
}
.crit-note {
  margin-top: 12px;
  color: #909399;
  font-size: 12px;
}
</style>
