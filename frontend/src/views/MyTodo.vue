<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { todoApi } from '../api'

const router = useRouter()
const loading = ref(false)
const data = ref(null)

const severityTagType = (s) => ({ 致命: 'danger', 严重: 'danger', 一般: 'warning', 提示: 'info' }[s] || 'info')
const defectStatusType = (s) => ({ 新建: 'info', 处理中: 'warning', 已修复: 'primary', 已验证: 'success', 关闭: '', 重新打开: 'danger' }[s] || 'info')
const priorityType = (p) => ({ P0: 'danger', P1: 'warning', P2: 'primary', P3: 'info' }[p] || 'info')

const groups = computed(() => {
  if (!data.value) return []
  const c = data.value.counts
  return [
    { key: 'review_cases', label: '待我评审', value: c.review_cases, hint: '去评审' },
    { key: 'my_defects', label: '指派给我的缺陷', value: c.my_defects, hint: '去修复' },
    { key: 'verify_defects', label: '待我验证的缺陷', value: c.verify_defects, hint: '去验证' },
    { key: 'rejected_cases', label: '被驳回待修改', value: c.rejected_cases, hint: '去修改' },
    { key: 'pending_cases', label: '负责批次待执行', value: c.pending_cases, hint: '去执行' },
    { key: 'my_plans', label: '我负责的批次', value: c.my_plans, hint: '看进度' },
  ]
})

async function load() {
  loading.value = true
  try {
    data.value = await todoApi.summary()
  } catch (e) {
    ElMessage.error('待办加载失败')
  } finally {
    loading.value = false
  }
}

function go(item) {
  if (!item.link) return
  router.push(item.link.startsWith('#') ? item.link.slice(1) : item.link)
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <template v-if="data">
      <el-row :gutter="12">
        <el-col v-for="g in groups" :key="g.key" :span="4">
          <el-card shadow="hover" class="stat-card">
            <div class="stat-value" :class="{ zero: g.value === 0 }">{{ g.value }}</div>
            <div class="stat-label">{{ g.label }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-alert
        v-if="data.total === 0 && data.unread_notifications === 0"
        type="success"
        :closable="false"
        show-icon
        title="当前没有需要你处理的待办"
        style="margin-top: 16px"
      />

      <el-card v-if="data.review_cases.length" shadow="hover" style="margin-top: 16px">
        <template #header>
          <span style="font-weight: 600">待我评审的用例</span>
          <span style="margin-left: 8px; color: #909399; font-size: 13px">
            共 {{ data.counts.review_cases }} 条
            <template v-if="data.counts.review_cases > data.review_cases.length">(仅显示前 {{ data.review_cases.length }} 条)</template>
          </span>
        </template>
        <el-table :data="data.review_cases" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="用例标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="project_name" label="项目" width="150" show-overflow-tooltip />
          <el-table-column label="优先级" width="90">
            <template #default="{ row }"><el-tag :type="priorityType(row.priority)" size="small">{{ row.priority }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="submitted_at" label="提交时间" width="150" />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }"><el-button link type="primary" @click="go(row)">去评审</el-button></template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-if="data.my_defects.length" shadow="hover" style="margin-top: 16px">
        <template #header>
          <span style="font-weight: 600">指派给我的缺陷</span>
          <span style="margin-left: 8px; color: #909399; font-size: 13px">
            共 {{ data.counts.my_defects }} 条
            <template v-if="data.counts.my_defects > data.my_defects.length">(仅显示前 {{ data.my_defects.length }} 条)</template>
          </span>
        </template>
        <el-table :data="data.my_defects" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="缺陷标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="project_name" label="项目" width="150" show-overflow-tooltip />
          <el-table-column label="严重程度" width="100">
            <template #default="{ row }"><el-tag :type="severityTagType(row.severity)" size="small">{{ row.severity }}</el-tag></template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }"><el-tag :type="defectStatusType(row.status)" size="small">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新" width="150" />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }"><el-button link type="primary" @click="go(row)">去处理</el-button></template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-if="data.verify_defects.length" shadow="hover" style="margin-top: 16px">
        <template #header>
          <span style="font-weight: 600">待我验证的缺陷</span>
          <span style="margin-left: 8px; color: #909399; font-size: 13px">
            我提交的缺陷已标记修复,需要复现验证
            <template v-if="data.counts.verify_defects > data.verify_defects.length">(仅显示前 {{ data.verify_defects.length }} 条)</template>
          </span>
        </template>
        <el-table :data="data.verify_defects" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="缺陷标题" min-width="220" show-overflow-tooltip />
          <el-table-column prop="project_name" label="项目" width="150" show-overflow-tooltip />
          <el-table-column label="严重程度" width="100">
            <template #default="{ row }"><el-tag :type="severityTagType(row.severity)" size="small">{{ row.severity }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="resolved_at" label="修复时间" width="150" />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }"><el-button link type="primary" @click="go(row)">去验证</el-button></template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-if="data.rejected_cases.length" shadow="hover" style="margin-top: 16px">
        <template #header>
          <span style="font-weight: 600">被驳回、需要我修改的用例</span>
        </template>
        <el-table :data="data.rejected_cases" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="project_name" label="项目" width="140" show-overflow-tooltip />
          <el-table-column prop="comment" label="评审意见" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }"><el-button link type="primary" @click="go(row)">去修改</el-button></template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-if="data.my_plans.length" shadow="hover" style="margin-top: 16px">
        <template #header>
          <span style="font-weight: 600">我负责的批次进度</span>
          <span style="margin-left: 8px; color: #909399; font-size: 13px">
            我是批次负责人或项目上的测试负责人
            <template v-if="data.plan_scanned">(已达 {{ data.my_plans.length }} 个批次上限,仅统计最近的批次)</template>
          </span>
        </template>
        <el-table :data="data.my_plans" size="small">
          <el-table-column prop="project_name" label="项目" width="150" show-overflow-tooltip />
          <el-table-column prop="version" label="批次" min-width="150" show-overflow-tooltip />
          <el-table-column prop="current_stage" label="当前阶段" width="100" />
          <el-table-column prop="stage_end" label="阶段截止" width="150" />
          <el-table-column label="剩余" width="110">
            <template #default="{ row }">
              <span v-if="row.remain_days === null" style="color: #909399">未设置</span>
              <el-tag v-else :type="row.overdue ? 'danger' : row.remain_days <= 3 ? 'warning' : 'success'" size="small">
                {{ row.overdue ? `已逾期 ${-row.remain_days} 天` : `${row.remain_days} 天` }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="待执行/总数" width="130">
            <template #default="{ row }">{{ row.pending }} / {{ row.total }}</template>
          </el-table-column>
          <el-table-column label="失败" width="80">
            <template #default="{ row }">
              <span :style="row.failed ? 'color:#f56c6c;font-weight:600' : ''">{{ row.failed }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }"><el-button link type="primary" @click="go(row)">看进度</el-button></template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-if="data.pending_cases.length" shadow="hover" style="margin-top: 16px">
        <template #header>
          <span style="font-weight: 600">当前阶段待执行用例</span>
          <span style="margin-left: 8px; color: #909399; font-size: 13px">
            共 {{ data.counts.pending_cases }} 条,按优先级排序
            <template v-if="data.counts.pending_cases > data.pending_cases.length">(仅显示前 {{ data.pending_cases.length }} 条)</template>
          </span>
        </template>
        <el-table :data="data.pending_cases" size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="project_name" label="项目" width="140" show-overflow-tooltip />
          <el-table-column prop="plan_version" label="批次" width="140" show-overflow-tooltip />
          <el-table-column prop="stage" label="阶段" width="80" />
          <el-table-column label="优先级" width="90">
            <template #default="{ row }"><el-tag :type="priorityType(row.priority)" size="small">{{ row.priority }}</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }"><el-button link type="primary" @click="go(row)">去执行</el-button></template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.stat-card {
  text-align: center;
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: #409eff;
  line-height: 1.4;
}
.stat-value.zero {
  color: #c0c4cc;
}
.stat-label {
  font-size: 13px;
  color: #606266;
}
</style>
