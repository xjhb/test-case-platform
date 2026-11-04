<template>
  <div class="notifications-page">
    <div class="page-header">
      <h2>我的通知</h2>
      <div class="header-actions">
        <el-radio-group v-model="readFilter" @change="reload">
          <el-radio-button :value="undefined">全部</el-radio-button>
          <el-radio-button :value="false">未读</el-radio-button>
          <el-radio-button :value="true">已读</el-radio-button>
        </el-radio-group>
        <el-select v-model="typeFilter" placeholder="全部类型" clearable style="width: 140px" @change="reload">
          <el-option v-for="(label, key) in TYPE_LABELS" :key="key" :label="label" :value="key" />
        </el-select>
        <el-button v-if="isAdmin" @click="scanStage" :loading="scanning">扫描到期提醒</el-button>
        <el-button @click="markAllRead" :disabled="unreadCount === 0">全部标记已读</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
      title="站内信始终记录;邮件与群机器人按通道配置尽力投递,外部通道失败不影响业务,只在这里显示投递情况"
    />

    <el-table :data="notifications" v-loading="loading" stripe>
      <el-table-column width="50">
        <template #default="{ row }">
          <span v-if="!row.is_read" class="unread-dot"></span>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
      <el-table-column prop="type" label="类型" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="typeTagColor(row.type)">{{ typeLabel(row.type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="content" label="内容" min-width="240" show-overflow-tooltip />
      <el-table-column prop="push_result" label="外部投递" width="170" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.push_result" :class="pushClass(row.push_result)">{{ row.push_result }}</span>
          <span v-else style="color: #c0c4cc">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="160">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="handleClick(row)" v-if="row.link">查看</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      class="pagination"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="handlePageChange"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { notificationApi } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')

const notifications = ref([])
const loading = ref(false)
const scanning = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const unreadCount = ref(0)
const readFilter = ref()
const typeFilter = ref('')

const TYPE_LABELS = {
  defect_assigned: '缺陷指派',
  defect_verify: '缺陷待验证',
  review_assigned: '用例待评审',
  review_result: '评审结果',
  stage_expiring: '阶段到期',
}

const TYPE_TAG = {
  defect_assigned: 'danger',
  defect_verify: 'warning',
  review_assigned: 'primary',
  review_result: 'success',
  stage_expiring: 'info',
}

const typeLabel = (t) => TYPE_LABELS[t] || t
const typeTagColor = (t) => TYPE_TAG[t] || 'info'

const pushClass = (text) => (text.includes('失败') || text.includes('未配置') ? 'push-bad' : 'push-ok')

const formatDate = (d) => {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN')
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await notificationApi.list({
      page: page.value,
      size: pageSize.value,
      is_read: readFilter.value,
      type: typeFilter.value || undefined,
    })
    notifications.value = res.items || []
    total.value = res.total || notifications.value.length
  } catch (e) { console.error(e) } finally { loading.value = false }
}

const loadUnreadCount = async () => {
  try {
    const res = await notificationApi.unreadCount()
    unreadCount.value = res.count || 0
  } catch (e) { console.error(e) }
}

const reload = () => {
  page.value = 1
  loadData()
}

const markAllRead = async () => {
  try {
    await notificationApi.markRead({ ids: [] })
    ElMessage.success('已全部标记为已读')
    loadData()
    loadUnreadCount()
  } catch (e) { console.error(e) }
}

const scanStage = async () => {
  scanning.value = true
  try {
    const res = await notificationApi.scanStage()
    ElMessage.success(res.message || '扫描完成')
    loadData()
    loadUnreadCount()
  } catch (e) { console.error(e) } finally { scanning.value = false }
}

const handleClick = (row) => {
  if (!row.is_read) {
    notificationApi.markRead({ ids: [row.id] })
    row.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }
  if (row.link) {
    // 兼容历史数据里 "#/xxx" 形式的链接
    router.push(row.link.startsWith('#') ? row.link.slice(1) : row.link)
  }
}

const handleDelete = async (row) => {
  try {
    await notificationApi.remove(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) { console.error(e) }
}

const handlePageChange = (p) => {
  page.value = p
  loadData()
}

onMounted(() => {
  loadData()
  loadUnreadCount()
})
</script>

<style scoped>
.notifications-page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.header-actions { display: flex; gap: 10px; align-items: center; }
.unread-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #f56c6c; }
.pagination { margin-top: 16px; justify-content: flex-end; }
.push-ok { color: #67c23a; }
.push-bad { color: #e6a23c; }
</style>
