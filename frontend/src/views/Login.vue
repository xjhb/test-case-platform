<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const formRef = ref()

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    const data = await authApi.login(form)
    auth.setAuth(data.access_token, {
      role: data.role,
      display_name: data.display_name,
    })
    // 存密码到期状态,供 MainLayout 登录后提醒
    localStorage.setItem('login_info', JSON.stringify({
      password_expiring: data.password_expiring || false,
      password_days_left: data.password_days_left,
      password_expired: data.password_expired || false,
      // 管理员重置过密码:必须先改密才能使用系统
      must_change_password: data.must_change_password || false,
    }))
    ElMessage.success('登录成功')
    router.push({ name: 'dashboard' })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="title">测管平台</h2>
      <p class="subtitle">测试用例管理平台</p>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="submit">登录</el-button>
      </el-form>

    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1e3c72, #2a5298);
}
.login-card {
  width: 380px;
  padding: 20px 10px;
}
.title {
  text-align: center;
  margin: 0 0 4px;
  color: #1e3c72;
  font-size: 26px;
}
.subtitle {
  text-align: center;
  margin: 0 0 24px;
  color: #909399;
  font-size: 13px;
}
.tip {
  margin-top: 14px;
  color: #c0c4cc;
  font-size: 12px;
  text-align: center;
}
</style>
