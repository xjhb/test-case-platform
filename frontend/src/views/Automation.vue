<template>
  <div class="automation-page">
    <div class="page-header">
      <h2>自动化测试集成</h2>
      <el-tag type="success" size="large">API文档</el-tag>
    </div>

    <el-card class="import-card">
      <template #header>
        <div class="card-header">
          <span>JUnit XML 结果导入</span>
          <span class="header-tip">上传 CI 产出的 results.xml,按用例标题或编号(如 TC-1024)匹配计划内用例后写入执行记录</span>
        </div>
      </template>

      <el-form :inline="true" class="import-form">
        <el-form-item label="项目">
          <el-select v-model="form.project_id" placeholder="选择项目" style="width: 180px" @change="onProjectChange">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="测试计划">
          <el-select v-model="form.plan_id" placeholder="选择批次" style="width: 200px">
            <el-option
              v-for="pl in planOptions"
              :key="pl.id"
              :label="`#${pl.id} ${pl.version} (${pl.current_stage}/${pl.status})`"
              :value="pl.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="form.stage" style="width: 100px">
            <el-option v-for="s in ['SIT', 'UAT', 'PRE']" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="执行环境">
          <el-select v-model="form.env_id" clearable placeholder="不指定" style="width: 170px">
            <el-option
              v-for="e in envOptions"
              :key="e.id"
              :label="`${e.name}(${e.stage})`"
              :value="e.id"
              :disabled="e.status === '已停用'"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="框架">
          <el-input v-model="form.framework" placeholder="Selenium/Playwright" style="width: 150px" />
        </el-form-item>
        <el-form-item label="构建号">
          <el-input v-model="form.build_number" placeholder="如 128" style="width: 110px" />
        </el-form-item>
        <el-form-item label="仅预览不落库">
          <el-switch v-model="form.dry_run" />
        </el-form-item>
      </el-form>

      <el-upload
        drag
        multiple
        accept=".xml"
        :auto-upload="false"
        v-model:file-list="fileList"
        class="xml-upload"
      >
        <div class="upload-tip">拖拽或点击选择 JUnit XML 文件(单次最多 20 个,单个不超过 10MB)</div>
      </el-upload>

      <div class="import-actions">
        <el-button :disabled="!canSubmit" :loading="importing" @click="submit(true)">解析预览</el-button>
        <el-button type="primary" :disabled="!canSubmit || form.dry_run" :loading="importing" @click="submit(false)">导入执行结果</el-button>
        <el-button v-if="fileList.length" @click="fileList = []">清空文件</el-button>
      </div>

      <div v-if="report" class="report">
        <div class="report-summary">
          <el-tag>解析 {{ report.total }} 条</el-tag>
          <el-tag type="success">匹配 {{ report.matched }} 条</el-tag>
          <el-tag type="warning">未匹配 {{ report.unmatched_total }} 条</el-tag>
          <el-tag v-if="!report.dry_run" type="primary">写入 {{ report.imported }} 条</el-tag>
          <el-tag v-for="(n, s) in report.by_status" :key="s" :type="statusTag(s)" effect="plain">{{ s }} {{ n }}</el-tag>
        </div>
        <el-alert v-if="report.dry_run" type="info" :closable="false" show-icon title="预览模式: 只解析和匹配,未写入任何执行记录" />
        <el-alert
          v-for="(e, i) in report.file_errors"
          :key="'e' + i"
          type="error"
          :closable="false"
          show-icon
          :title="`${e.file}: ${e.error}`"
        />
        <el-table v-if="report.unmatched.length" :data="report.unmatched" size="small" stripe style="margin-top: 12px">
          <el-table-column prop="name" label="XML 中的用例名" min-width="220" show-overflow-tooltip />
          <el-table-column prop="file" label="来源文件" width="160" show-overflow-tooltip />
          <el-table-column prop="status" label="结果" width="80">
            <template #default="{ row }"><el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="reason" label="未匹配原因" min-width="220" show-overflow-tooltip />
        </el-table>
      </div>
    </el-card>

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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { automationApi, planApi, projectApi, envApi } from '../api'

const loading = ref(false)
const guide = ref(null)
const activeTab = ref('curl')

const projects = ref([])
const plans = ref([])
const fileList = ref([])
const importing = ref(false)
const report = ref(null)

const form = reactive({
  project_id: null,
  plan_id: null,
  stage: 'SIT',
  env_id: null,
  framework: '',
  build_number: '',
  dry_run: false,
})

const envOptions = ref([])

async function onProjectChange() {
  form.plan_id = null
  form.env_id = null
  if (!form.project_id) {
    envOptions.value = []
    return
  }
  envOptions.value = await envApi.list({ project_id: form.project_id }).catch(() => [])
}

const planOptions = computed(() =>
  form.project_id ? plans.value.filter((p) => p.project_id === form.project_id) : plans.value
)

const canSubmit = computed(() => !!form.plan_id && fileList.value.length > 0)

const statusTag = (s) => ({ 通过: 'success', 失败: 'danger', 阻塞: 'warning' }[s] || 'info')

async function loadBase() {
  try {
    const [ps, pls] = await Promise.all([projectApi.list(), planApi.list()])
    projects.value = Array.isArray(ps) ? ps : ps.items || []
    plans.value = Array.isArray(pls) ? pls : pls.items || []
  } catch (e) {
    console.error(e)
  }
}

async function submit(dryRun) {
  const fd = new FormData()
  fileList.value.forEach((f) => {
    if (f.raw) fd.append('files', f.raw)
  })
  fd.append('plan_id', String(form.plan_id))
  fd.append('stage', form.stage)
  if (form.env_id) fd.append('env_id', String(form.env_id))
  fd.append('framework', form.framework || '')
  fd.append('build_number', form.build_number || '')
  fd.append('dry_run', dryRun ? 'true' : 'false')
  importing.value = true
  try {
    report.value = await automationApi.importXml(fd)
    if (dryRun) {
      ElMessage.success(`解析完成: 匹配 ${report.value.matched}/${report.value.total}`)
    } else {
      ElMessage.success(`已导入 ${report.value.imported} 条执行结果`)
    }
  } catch (e) {
    console.error(e)
  } finally {
    importing.value = false
  }
}

const requestFields = computed(() => {
  if (!guide.value) return []
  const body = guide.value.request_body
  return [
    { field: 'plan_id', type: 'integer', required: true, description: '测试计划ID' },
    { field: 'stage', type: 'string', required: false, description: '执行阶段: SIT/UAT/PRE (默认SIT)' },
    { field: 'env_id', type: 'integer', required: false, description: '执行环境ID,须属于该计划所属项目' },
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
  loadBase()
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

.import-card {
  max-width: 1200px;
  margin-bottom: 20px;
}

.header-tip {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.import-form {
  margin-bottom: 4px;
}

.xml-upload {
  width: 100%;
}

.upload-tip {
  color: #606266;
  padding: 6px 0;
}

.import-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.report {
  margin-top: 16px;
}

.report-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
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
