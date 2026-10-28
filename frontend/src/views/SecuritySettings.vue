<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '../api'

const loading = ref(false)
const form = reactive({
  session_timeout_minutes: 30,
  password_expire_days: 30,
  password_remind_days: 10,
})

async function load() {
  loading.value = true
  try {
    const cfg = await systemApi.getConfig()
    form.session_timeout_minutes = cfg.session_timeout_minutes
    form.password_expire_days = cfg.password_expire_days
    form.password_remind_days = cfg.password_remind_days
  } finally {
    loading.value = false
  }
}

async function save() {
  // 验证登录超时
  if (form.session_timeout_minutes < 1 || form.session_timeout_minutes > 1440) {
    ElMessage.error('登录超时需要 1~1440 分钟')
    return
  }
  // 验证密码有效期
  if (form.password_expire_days < 1 || form.password_expire_days > 365) {
    ElMessage.error('密码有效期需要 1~365 天')
    return
  }
  // 验证提醒天数
  if (form.password_remind_days < 1 || form.password_remind_days > form.password_expire_days) {
    ElMessage.error('提醒天数需要 1 到 有效期之间')
    return
  }

  await systemApi.updateConfig({
    session_timeout_minutes: form.session_timeout_minutes,
    password_expire_days: form.password_expire_days,
    password_remind_days: form.password_remind_days,
  })
  ElMessage.success('安全配置已保存')
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="hover" style="max-width: 720px">
      <template #header>
        <span style="font-weight: 600; font-size: 16px">安全登录配置</span>
      </template>

      <!-- 登录超时 -->
      <el-divider content-position="left">登录超时设置</el-divider>
      <el-form label-width="180px" :model="form">
        <el-form-item label="登录超时(分钟)">
          <el-input-number
            v-model="form.session_timeout_minutes"
            :min="1"
            :max="1440"
            :step="5"
            style="width: 200px"
          />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">
            超过此时间无操作，自动退出登录
          </span>
        </el-form-item>
      </el-form>

      <!-- 密码策略 -->
      <el-divider content-position="left">密码策略</el-divider>
      <el-form label-width="180px" :model="form">
        <el-form-item label="密码有效期(天)">
          <el-input-number
            v-model="form.password_expire_days"
            :min="1"
            :max="365"
            :step="1"
            style="width: 200px"
          />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">
            到期后必须修改密码
          </span>
        </el-form-item>
        <el-form-item label="提前提醒(天)">
          <el-input-number
            v-model="form.password_remind_days"
            :min="1"
            :max="365"
            :step="1"
            style="width: 200px"
          />
          <span style="margin-left: 12px; color: #909399; font-size: 13px">
            到期前 N 天开始提醒
          </span>
        </el-form-item>
      </el-form>

      <!-- 保存按钮 -->
      <el-form-item style="margin-top: 24px">
        <el-button type="primary" @click="save" :loading="loading">保存配置</el-button>
      </el-form-item>

      <!-- 说明 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="说明：修改后对下次登录的用户生效。已登录用户在 token 过期或密码到期时会被要求重新认证。"
      />
    </el-card>
  </div>
</template>

<style scoped>
.el-divider__text {
  font-weight: 600;
  color: #303133;
}
</style>
