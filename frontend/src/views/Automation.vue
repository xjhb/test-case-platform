<template>
  <div class="automation-page">
    <div class="page-header">
      <h2>自动化测试集成</h2>
      <el-tag type="success" size="large">API文档</el-tag>
    </div>

    <el-card v-loading="loading" class="guide-card">
      <template #header>
        <div class="card-header">
          <span>集成指南</span>
        </div>
      </template>

      <div v-if="guide" class="guide-content">
        <el-alert :title="guide.title" type="info" :closable="false" show-icon style="margin-bottom: 20px">
          {{ guide.description }}
        </el-alert>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="API端点">
            <el-tag type="primary">{{ guide.api_endpoint }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="请求方法">
            <el-tag type="success">{{ guide.method }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="认证方式" :span="2">
            {{ guide.authentication }}
          </el-descriptions-item>
        </el-descriptions>

        <h3 style="margin-top: 24px; margin-bottom: 12px">请求参数</h3>
        <el-table :data="requestFields" border stripe>
          <el-table-column prop="field" label="字段" width="180" />
          <el-table-column prop="type" label="类型" width="120" />
          <el-table-column prop="required" label="必填" width="80">
            <template #default="{ row }">
              <el-tag :type="row.required ? 'danger' : 'info'" size="small">
                {{ row.required ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" />
        </el-table>

        <h3 style="margin-top: 24px; margin-bottom: 12px">使用示例</h3>

        <el-tabs v-model="activeTab">
          <el-tab-pane label="cURL" name="curl">
            <div class="code-block">
              <pre><code>{{ guide.example.curl }}</code></pre>
              <el-button class="copy-btn" type="primary" size="small" @click="copyCode(guide.example.curl)">
                复制
              </el-button>
            </div>
          </el-tab-pane>
          <el-tab-pane label="Python" name="python">
            <div class="code-block">
              <pre><code>{{ guide.example.python }}</code></pre>
              <el-button class="copy-btn" type="primary" size="small" @click="copyCode(guide.example.python)">
                复制
              </el-button>
            </div>
          </el-tab-pane>
        </el-tabs>

        <h3 style="margin-top: 24px; margin-bottom: 12px">注意事项</h3>
        <el-alert
          v-for="(note, index) in guide.notes"
          :key="index"
          :title="note"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 8px"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { automationApi } from '../api'

const loading = ref(false)
const guide = ref(null)
const activeTab = ref('curl')

const requestFields = computed(() => {
  if (!guide.value) return []
  const body = guide.value.request_body
  return [
    { field: 'plan_id', type: 'integer', required: true, description: '测试计划ID' },
    { field: 'stage', type: 'string', required: false, description: '执行阶段: SIT/UAT/PRE (默认SIT)' },
    { field: 'framework', type: 'string', required: false, description: '自动化框架名称' },
    { field: 'build_number', type: 'string', required: false, description: '构建号' },
    { field: 'results', type: 'array', required: true, description: '测试结果列表' },
    { field: 'results[].testcase_id', type: 'integer', required: true, description: '用例ID' },
    { field: 'results[].status', type: 'string', required: true, description: '执行结果: 通过/失败/阻塞' },
    { field: 'results[].remark', type: 'string', required: false, description: '备注' },
    { field: 'results[].screenshot', type: 'string', required: false, description: '截图URL' },
    { field: 'results[].duration_seconds', type: 'integer', required: false, description: '执行时长(秒)' },
    { field: 'results[].executed_at', type: 'string', required: false, description: '执行时间(ISO格式)' },
  ]
})

async function loadGuide() {
  loading.value = true
  try {
    guide.value = await automationApi.guide()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function copyCode(code) {
  navigator.clipboard.writeText(code).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

onMounted(() => {
  loadGuide()
})
</script>

<style scoped>
.automation-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
}

.guide-card {
  max-width: 1200px;
}

.card-header {
  font-weight: 600;
  font-size: 16px;
}

.guide-content h3 {
  color: #303133;
  font-size: 16px;
}

.code-block {
  position: relative;
  background: #f5f7fa;
  border-radius: 4px;
  padding: 16px;
  margin-top: 12px;
}

.code-block pre {
  margin: 0;
  overflow-x: auto;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.code-block code {
  color: #303133;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
}
</style>
