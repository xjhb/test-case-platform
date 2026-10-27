<template>
  <div class="notifications-page">
    <div class="page-header">
      <h2>我的通知</h2>
      <el-button @click="markAllRead" :disabled="unreadCount === 0">全部标记已读</el-button>
    </div>

    <el-table :data="notifications" v-loading="loading" stripe>
      <el-table-column width="50">
        <template #default="{ row }">
          <span v-if="!row.is_read" class="unread-dot"></span>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="250" show-overflow-tooltip />
      <el-table-column prop="type" label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="typeTagColor(row.type)">{{ typeLabel(row.type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="content" label="内容" min-width="300" show-overflow-tooltip />
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
      v-if="total > 0"
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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { notificationApi } from '../api'

const router = useRouter()
const notifications = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const unreadCount = ref(0)

const typeLabel = (t) => {
  const map = { defect_assigned: '缺陷指派', testcase_assigned: '用例分配', stage_expiring: '阶段到期', mention: '提及' }
  return map[t] || t
}

const typeTagColor = (t) => {
  const map = { defect_assigned: 'danger', testcase_assigned: 'warning', stage_expiring: 'info', mention: 'success' }
  return map[t] || 'info'
}

const formatDate = (d) => {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN')
}

const loadData = async () => {
  loading.value = true
  try {
    const res = await notificationApi.list({ page: page.value, size: pageSize.value })
    notifications.value = Array.isArray(res) ? res : (res.items || [])
    total.value = res.total || notifications.value.length
  } catch (e) { console.error(e) } finally { loading.value = false }
}

const loadUnreadCount = async () => {
  try {
    const res = await notificationApi.unreadCount()
    unreadCount.value = res.count || 0
  } catch (e) { console.error(e) }
}

const markAllRead = async () => {
  try {
    await notificationApi.markRead({ ids: [] })
    ElMessage.success('已全部标记为已读')
    loadData()
    loadUnreadCount()
  } catch (e) { console.error(e) }
}

const handleClick = (row) => {
  if (!row.is_read) {
    notificationApi.markRead({ ids: [row.id] })
    row.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }
  if (row.link) {
    router.push(row.link)
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
.unread-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #f56c6c; }
.pagination { margin-top: 16px; justify-content: flex-end; }
</style>
