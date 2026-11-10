<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { logApi } from '../api'

const list = ref([])
const total = ref(0)
const loading = ref(false)
const actions = ref([])
const chain = ref(null)          // 链头概况
const report = ref(null)         // 最近一次校验结果
const verifying = ref(false)
const anchorDate = ref(new Date().toISOString().slice(0, 10))
const anchor = ref(null)
const anchoring = ref(false)

const query = reactive({
  action: '',
  username: '',
  page: 1,
  page_size: 20,
})

const actionTagType = (a) => ({
  登录: 'info', 创建: 'success', 编辑: 'primary', 删除: 'danger',
  执行: 'warning', 推进: 'warning', 导入: 'primary', 导出: 'success', 分配: 'primary',
  校验: 'warning',
}[a] || 'info')

const issueType = (k) => ({
  内容被篡改: 'danger', 链断裂: 'danger', 未入链: 'warning', 链头不符: 'danger',
}[k] || 'info')

const shortHash = (h) => (h ? `${h.slice(0, 8)}…${h.slice(-4)}` : '未入链')

async function loadActions() {
  actions.value = await logApi.actions()
}

async function loadChain() {
  chain.value = await logApi.state()
}

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, page_size: query.page_size }
    if (query.action) params.action = query.action
    if (query.username) params.username = query.username
    const res = await logApi.list(params)
    list.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function runVerify(leaveTrace) {
  verifying.value = true
  try {
    report.value = leaveTrace ? await logApi.verify() : await logApi.integrity()
    if (report.value.ok) {
      ElMessage.success(`链完整: ${report.value.checked} 条日志逐条重算通过`)
    } else {
      ElMessage.error(`检出 ${report.value.issues.length} 处异常,见下方明细`)
    }
    await loadChain()
    if (leaveTrace) load()
  } finally {
    verifying.value = false
  }
}

async function genAnchor() {
  anchoring.value = true
  try {
    anchor.value = await logApi.anchor(anchorDate.value)
    if (!anchor.value.count) ElMessage.warning('该日期没有日志记录')
  } finally {
    anchoring.value = false
  }
}

async function copyAnchor() {
  try {
    await navigator.clipboard.writeText(anchor.value.anchor)
    ElMessage.success('锚定值已复制')
  } catch {
    ElMessage.warning('浏览器拒绝了剪贴板写入,请手动选中复制')
  }
}

function search() {
  query.page = 1
  load()
}

function pageChange(p) {
  query.page = p
  load()
}
function sizeChange(s) {
  query.page_size = s
  query.page = 1
  load()
}

onMounted(async () => {
  await loadActions()
  loadChain()
  load()
})
</script>

<template>
  <div>
    <el-alert type="info" :closable="false" style="margin-bottom: 12px">
      <template #title>
        <div style="display: flex; flex-wrap: wrap; gap: 8px; align-items: center">
          <span style="font-weight: 600">审计日志完整性</span>
          <el-tag v-if="chain" size="small" type="info">已入链 {{ chain.log_count }} 条</el-tag>
          <el-tag v-if="chain" size="small" type="info">末条 #{{ chain.last_log_id }}</el-tag>
          <el-tag v-if="chain" size="small">链头 {{ shortHash(chain.head_hash) }}</el-tag>
          <el-tooltip v-if="chain && chain.salt_source === 'secret_key'"
                      content="未单独配置 AUDIT_SECRET,哈希盐复用 JWT 签名密钥:轮换 SECRET_KEY 会让历史链校验失败,生产环境建议单独配置">
            <el-tag size="small" type="warning">未配置独立审计密钥</el-tag>
          </el-tooltip>
        </div>
      </template>
      <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 8px">
        <el-button size="small" type="primary" :loading="verifying" @click="runVerify(false)">校验整链</el-button>
        <el-button size="small" :loading="verifying" @click="runVerify(true)">留痕校验</el-button>
        <el-divider direction="vertical" />
        <el-date-picker v-model="anchorDate" type="date" value-format="YYYY-MM-DD" size="small"
                        placeholder="按日锚定" style="width: 140px" :clearable="false" />
        <el-button size="small" :loading="anchoring" @click="genAnchor">生成锚定值</el-button>
        <template v-if="anchor && anchor.count">
          <span style="font-family: monospace; font-size: 12px">{{ shortHash(anchor.anchor) }}</span>
          <el-button size="small" link type="primary" @click="copyAnchor">复制</el-button>
          <span style="color: #909399; font-size: 12px">{{ anchor.date }} 共 {{ anchor.count }} 条 ({{ anchor.first_id }}~{{ anchor.last_id }})</span>
        </template>
      </div>
      <div v-if="report" style="margin-top: 8px">
        <el-alert :type="report.ok ? 'success' : 'error'" :closable="false" show-icon>
          <template #title>
            {{ report.ok ? `校验通过: ${report.checked} 条日志 (#${report.from_id}~#${report.to_id}) 哈希链连续且内容未被改动`
              : `校验异常: 共 ${report.checked} 条, 检出 ${report.issues.length} 处问题${report.truncated ? '(仅显示前 50 处)' : ''}` }}
          </template>
        </el-alert>
      </div>
    </el-alert>

    <div class="filter">
      <el-select v-model="query.action" placeholder="操作类型" clearable style="width: 140px" @change="search">
        <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
      </el-select>
      <el-input v-model="query.username" placeholder="用户名" clearable style="width: 160px" @keyup.enter="search" />
      <el-button type="primary" @click="search">查询</el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table v-if="report && report.issues.length" :data="report.issues" border size="small"
              style="margin-bottom: 14px">
      <el-table-column prop="id" label="日志ID" width="90" />
      <el-table-column label="异常类型" width="120">
        <template #default="{ row }">
          <el-tag :type="issueType(row.kind)" size="small">{{ row.kind }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reason" label="说明" min-width="320" show-overflow-tooltip />
    </el-table>

    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-tag :type="actionTagType(row.action)" size="small">{{ row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="用户" width="120" />
      <el-table-column prop="target" label="操作对象" min-width="180" show-overflow-tooltip />
      <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
      <el-table-column prop="ip" label="IP" width="130" />
      <el-table-column prop="created_at" label="时间" width="170">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
        </template>
      </el-table-column>
      <el-table-column label="链上哈希" width="140">
        <template #default="{ row }">
          <el-tooltip placement="left">
            <template #content>
              本条: {{ row.row_hash || '未入链' }}<br />前序: {{ row.prev_hash || '未入链' }}
            </template>
            <span style="font-family: monospace; font-size: 12px">{{ shortHash(row.row_hash) }}</span>
          </el-tooltip>
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
  </div>
</template>

<style scoped>
.filter {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
  display: flex;
}
</style>
