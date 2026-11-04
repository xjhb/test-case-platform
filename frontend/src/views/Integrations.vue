<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { integrationApi } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const loading = ref(false)
const status = ref({ channels: [], webhook_secret_configured: false, platform_base_url_configured: false, external_push_enabled: true, config_source: 'env', hint: '' })
const testing = ref('')

const events = ref([])
const eventsLoading = ref(false)

const KIND_LABELS = { notification: '通知渠道', cicd: 'CI/CD', issue: '缺陷系统' }

const groups = computed(() => {
  const out = []
  for (const kind of ['notification', 'cicd', 'issue']) {
    const items = status.value.channels.filter((c) => c.kind === kind)
    if (items.length) out.push({ kind, label: KIND_LABELS[kind], items })
  }
  return out
})

const configuredCount = computed(() => status.value.channels.filter((c) => c.configured).length)

async function load() {
  loading.value = true
  try {
    status.value = await integrationApi.status()
  } finally {
    loading.value = false
  }
}

async function loadEvents() {
  eventsLoading.value = true
  try {
    events.value = await integrationApi.webhookEvents(30)
  } finally {
    eventsLoading.value = false
  }
}

async function runSelfTest(row) {
  testing.value = row.name
  try {
    const res = await integrationApi.selfTest(row.name)
    ElMessage.success(`${row.label}: ${res.message || '连通性校验通过'}`)
  } catch (e) {
    // 拦截器已弹出后端 detail,这里只负责刷新状态;不再重复提示
  } finally {
    testing.value = ''
    await load()
  }
}

onMounted(() => {
  load()
  loadEvents()
})
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button @click="load">刷新</el-button>
      <el-button @click="loadEvents">刷新回调记录</el-button>
    </div>

    <el-alert
      title="外部集成凭据只来自 backend/.env 或 Nacos"
      :description="status.hint || '本页只做只读展示与连通性自检,不提供在线改凭据'"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <div class="summary">
      <span>已接通 {{ configuredCount }} / {{ status.channels.length }} 个通道</span>
      <el-tag size="small" :type="status.config_source === 'nacos' ? 'success' : 'info'">
        配置来源: {{ status.config_source === 'nacos' ? 'Nacos' : '本地 .env' }}
      </el-tag>
      <el-tag size="small" :type="status.webhook_secret_configured ? 'success' : 'warning'">
        回调密钥 {{ status.webhook_secret_configured ? '已配置' : '未配置' }}
      </el-tag>
      <el-tag size="small" :type="status.platform_base_url_configured ? 'success' : 'info'">
        平台外访地址 {{ status.platform_base_url_configured ? '已配置' : '未配置' }}
      </el-tag>
      <el-tag size="small" :type="status.external_push_enabled ? 'success' : 'warning'">
        外部投递 {{ status.external_push_enabled ? '已开启' : '已关闭(仅站内信)' }}
      </el-tag>
    </div>

    <div v-loading="loading">
      <div v-for="group in groups" :key="group.kind" class="group">
        <h3>{{ group.label }}</h3>
        <el-table :data="group.items" border>
          <el-table-column prop="label" label="通道" width="180" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="row.configured ? 'success' : 'info'" size="small">
                {{ row.configured ? '已配置' : '未配置' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="缺失的配置项">
            <template #default="{ row }">
              <span v-if="row.configured" class="muted">-</span>
              <el-tag v-for="k in row.missing_keys" :key="k" size="small" type="warning" class="key-tag">{{ k }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.has_probe && auth.role === 'admin'"
                size="small"
                :type="row.configured ? 'primary' : 'info'"
                :disabled="!row.configured"
                :loading="testing === row.name"
                @click="runSelfTest(row)"
              >
                连通性自检
              </el-button>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <el-alert
      v-if="auth.role === 'admin'"
      title="钉钉/企业微信/飞书的自检会真实推送一条测试消息到群里"
      type="warning"
      :closable="false"
      show-icon
      style="margin: 16px 0"
    />

    <h3>最近回调事件</h3>
    <el-table v-loading="eventsLoading" :data="events" border empty-text="暂无回调记录">
      <el-table-column prop="source" label="来源" width="110" />
      <el-table-column prop="event_type" label="事件" width="150" />
      <el-table-column prop="external_key" label="外部主键" width="140" />
      <el-table-column label="处理结果" width="120">
        <template #default="{ row }">
          <el-tag
            size="small"
            :type="row.handle_result === '处理失败' || row.handle_result === '未识别' ? 'danger' : row.handle_result === '已忽略' ? 'info' : 'success'"
          >
            {{ row.handle_result }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="handle_note" label="说明" min-width="240" show-overflow-tooltip />
      <el-table-column label="接收时间" width="180">
        <template #default="{ row }">{{ new Date(row.received_at).toLocaleString() }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.toolbar {
  margin-bottom: 16px;
  display: flex;
  gap: 10px;
}
.summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  font-weight: 600;
}
.group {
  margin-bottom: 20px;
}
.group h3,
h3 {
  margin: 18px 0 10px;
  font-size: 15px;
}
.key-tag {
  margin-right: 6px;
}
.muted {
  color: #909399;
}
</style>
