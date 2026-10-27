<template>
  <div class="versions-page">
    <div class="page-header">
      <h2>用例版本历史 - {{ testcaseTitle }}</h2>
      <el-button @click="goBack">返回</el-button>
    </div>

    <el-timeline>
      <el-timeline-item
        v-for="v in versions"
        :key="v.id"
        :timestamp="formatDate(v.changed_at)"
        placement="top"
        :type="v.version === currentVersion ? 'primary' : ''"
      >
        <el-card>
          <div class="version-header">
            <span class="version-num">版本 {{ v.version }}</span>
            <el-tag size="small">{{ v.priority }}</el-tag>
            <span class="changer">{{ v.changed_by_name }}</span>
            <span class="summary" v-if="v.change_summary">{{ v.change_summary }}</span>
          </div>
          <div class="version-content">
            <p><strong>模块:</strong> {{ v.module || '-' }}</p>
            <p><strong>标题:</strong> {{ v.title }}</p>
            <p><strong>前置条件:</strong> {{ v.precondition || '-' }}</p>
            <p><strong>测试步骤:</strong></p>
            <pre class="steps">{{ v.steps || '-' }}</pre>
            <p><strong>预期结果:</strong> {{ v.expected || '-' }}</p>
          </div>
          <div class="version-actions" v-if="v.version !== currentVersion">
            <el-button size="small" type="warning" @click="handleRollback(v)">回滚到此版本</el-button>
          </div>
        </el-card>
      </el-timeline-item>
    </el-timeline>

    <el-empty v-if="versions.length === 0" description="暂无版本历史" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { versionApi, testcaseApi } from '../api'

const route = useRoute()
const router = useRouter()
const versions = ref([])
const testcaseTitle = ref('')
const currentVersion = ref(0)

const formatDate = (d) => {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN')
}

const loadVersions = async () => {
  const testcaseId = route.params.id
  try {
    const tc = await testcaseApi.get(testcaseId)
    testcaseTitle.value = tc.title

    const vers = await versionApi.list(testcaseId)
    versions.value = vers
    currentVersion.value = vers.length > 0 ? Math.max(...vers.map(v => v.version)) : 0
  } catch (e) { console.error(e) }
}

const handleRollback = async (v) => {
  try {
    await ElMessageBox.confirm(`确定回滚到版本 ${v.version}? 当前内容将被保存为新版本。`, '提示', { type: 'warning' })
    await versionApi.rollback(route.params.id, v.id)
    ElMessage.success(`已回滚到版本 ${v.version}`)
    loadVersions()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}

const goBack = () => {
  router.back()
}

onMounted(loadVersions)
</script>

<style scoped>
.versions-page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 18px; }
.version-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.version-num { font-weight: bold; font-size: 16px; color: #409eff; }
.changer { color: #909399; font-size: 13px; }
.summary { color: #606266; font-size: 13px; font-style: italic; }
.version-content { margin: 10px 0; }
.version-content p { margin: 6px 0; }
.steps { background: #f5f7fa; padding: 10px; border-radius: 4px; white-space: pre-wrap; font-size: 13px; }
.version-actions { margin-top: 10px; }
</style>
