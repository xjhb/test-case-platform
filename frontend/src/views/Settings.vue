<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '../api'

const loading = ref(false)
const form = reactive({ session_timeout_minutes: 30 })

async function load() {
  loading.value = true
  try {
    const cfg = await systemApi.getConfig()
    form.session_timeout_minutes = cfg.session_timeout_minutes
  } finally {
    loading.value = false
  }
}

async function save() {
  if (form.session_timeout_minutes < 1 || form.session_timeout_minutes > 1440) {
    ElMessage.error('超时时间需在 1~1440 分钟之间')
    return
  }
  await systemApi.updateConfig({ session_timeout_minutes: form.session_timeout_minutes })
  ElMessage.success('已保存,下次登录生效')
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="hover" style="max-width: 560px">
      <template #header><span style="font-weight: 600">登录超时配置</span></template>
      <el-form label-width="160px">
        <el-form-item label="登录超时(分钟)">
          <el-input-number v-model="form.session_timeout_minutes" :min="1" :max="1440" :step="5" />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">
            超过此时间无操作,自动退出登录
          </span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="说明:修改后对下次登录的用户生效。已登录的用户在 token 过期后会被自动退出。"
      />
    </el-card>
  </div>
</template>
