<script setup>
import { ref, reactive, onMounted } from 'vue'
import { logApi } from '../api'

const list = ref([])
const total = ref(0)
const loading = ref(false)
const actions = ref([])

const query = reactive({
  action: '',
  username: '',
  page: 1,
  page_size: 20,
})

const actionTagType = (a) => ({
  登录: 'info', 创建: 'success', 编辑: 'primary', 删除: 'danger',
  执行: 'warning', 推进: 'warning', 导入: 'primary', 导出: 'success', 分配: 'primary',
}[a] || 'info')

async function loadActions() {
  actions.value = await logApi.actions()
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
  load()
})
</script>

<template>
  <div>
    <div class="filter">
      <el-select v-model="query.action" placeholder="操作类型" clearable style="width: 140px">
        <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
      </el-select>
      <el-input v-model="query.username" placeholder="用户名" clearable style="width: 160px" @keyup.enter="search" />
      <el-button type="primary" @click="search">查询</el-button>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-tag :type="actionTagType(row.action)" size="small">{{ row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="用户" width="120" />
      <el-table-column prop="target" label="操作对象" min-width="200" show-overflow-tooltip />
      <el-table-column prop="detail" label="详情" min-width="220" show-overflow-tooltip />
      <el-table-column prop="ip" label="IP" width="130" />
      <el-table-column prop="created_at" label="时间" width="180">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
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
