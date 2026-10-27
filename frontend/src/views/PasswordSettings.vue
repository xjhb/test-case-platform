<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '../api'

const loading = ref(false)
const form = reactive({ password_expire_days: 30, password_remind_days: 10 })

async function load() {
  loading.value = true
  try {
    const cfg = await systemApi.getConfig()
    form.password_expire_days = cfg.password_expire_days
    form.password_remind_days = cfg.password_remind_days
  } finally {
    loading.value = false
  }
}

async function save() {
  if (form.password_expire_days < 1 || form.password_expire_days > 365) {
    ElMessage.error('密码有效期需在 1~365 天之间')
    return
  }
  if (form.password_remind_days < 1 || form.password_remind_days > form.password_expire_days) {
    ElMessage.error('提醒天数需在 1 到 有效期 之间')
    return
  }
  await systemApi.updateConfig({
    password_expire_days: form.password_expire_days,
    password_remind_days: form.password_remind_days,
  })
  ElMessage.success('已保存,对下次登录生效')
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="hover" style="max-width: 560px">
      <template #header><span style="font-weight: 600">密码到期配置</span></template>
      <el-form label-width="160px">
        <el-form-item label="密码有效期(天)">
          <el-input-number v-model="form.password_expire_days" :min="1" :max="365" :step="1" />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">到期后必须修改密码</span>
        </el-form-item>
        <el-form-item label="提前提醒(天)">
          <el-input-number v-model="form.password_remind_days" :min="1" :max="365" :step="1" />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">到期前N天开始提醒</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="说明:默认密码30天有效,到期前10天登录时弹出提醒。到期后强制修改密码才能继续使用。"
      />
    </el-card>
  </div>
</template>
