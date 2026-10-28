<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const activeTab = ref('password')
const isForcedChange = ref(false)

// 检查是否处于强制改密状态
onMounted(() => {
  const data = JSON.parse(localStorage.getItem('login_info') || '{}')
  if (data.must_change_password) {
    isForcedChange.value = true
  }
})

// 修改密码表单
const pwdFormRef = ref()
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [{ required: true, min: 6, message: '至少6位', trigger: 'blur' }],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== pwdForm.new_password) callback(new Error('两次输入不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

async function submitPassword() {
  await pwdFormRef.value.validate()
  await authApi.changePassword({
    old_password: pwdForm.old_password,
    new_password: pwdForm.new_password,
  })
  ElMessage.success('密码已修改')
  
  // 如果是强制改密，清除标记并刷新页面
  if (isForcedChange.value) {
    try {
      const info = JSON.parse(localStorage.getItem('login_info') || '{}')
      info.must_change_password = false
      info.password_expired = false
      localStorage.setItem('login_info', JSON.stringify(info))
    } catch (e) {
      localStorage.removeItem('login_info')
    }
    ElMessage.success('密码修改成功，系统将重新加载')
    setTimeout(() => location.reload(), 1000)
    return
  }
  
  pwdForm.old_password = ''
  pwdForm.new_password = ''
  pwdForm.confirm_password = ''
}

// 个人信息表单
const userInfo = reactive({
  username: auth.username || '',
  display_name: auth.displayName || '',
  email: '',
  phone: '',
})

// 加载用户信息
async function loadUserInfo() {
  try {
    const user = await authApi.me()
    userInfo.username = user.username
    userInfo.display_name = user.display_name || ''
    userInfo.email = user.email || ''
    userInfo.phone = user.phone || ''
  } catch (e) {
    console.error('加载用户信息失败:', e)
  }
}

async function saveUserInfo() {
  try {
    await authApi.updateProfile({
      display_name: userInfo.display_name,
      email: userInfo.email,
      phone: userInfo.phone,
    })
    ElMessage.success('个人信息已保存')
    // 更新本地存储的显示名称
    const user = JSON.parse(localStorage.getItem('user') || '{}')
    user.display_name = userInfo.display_name
    localStorage.setItem('user', JSON.stringify(user))
    // 刷新页面以更新头部显示
    setTimeout(() => location.reload(), 500)
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

// 组件挂载时加载数据
onMounted(() => {
  const data = JSON.parse(localStorage.getItem('login_info') || '{}')
  if (data.must_change_password) {
    isForcedChange.value = true
  } else {
    loadUserInfo()
  }
})
</script>

<template>
  <div>
    <el-card shadow="hover">
      <el-tabs v-model="activeTab" :closable="false">
        <!-- 修改密码页签 -->
        <el-tab-pane label="修改密码" name="password">
          <el-alert
            v-if="isForcedChange"
            type="error"
            :closable="false"
            show-icon
            title="必须修改密码"
            description="您的密码已被管理员重置，修改密码后才能继续使用系统。"
            style="margin-bottom: 20px"
          />
          <el-form
            ref="pwdFormRef"
            :model="pwdForm"
            :rules="pwdRules"
            label-width="100px"
            style="max-width: 500px; margin-top: 20px"
          >
            <el-form-item label="原密码" prop="old_password">
              <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入原密码" />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少6位" />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm_password">
              <el-input v-model="pwdForm.confirm_password" type="password" show-password placeholder="再次输入新密码" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitPassword">确认修改</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 个人信息页签（预留，强制改密时隐藏） -->
        <el-tab-pane v-if="!isForcedChange" label="个人信息" name="info">
          <el-form :model="userInfo" label-width="100px" style="max-width: 500px; margin-top: 20px">
            <el-form-item label="用户名">
              <el-input v-model="userInfo.username" disabled />
            </el-form-item>
            <el-form-item label="显示名称">
              <el-input v-model="userInfo.display_name" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="userInfo.email" />
            </el-form-item>
            <el-form-item label="手机号">
              <el-input v-model="userInfo.phone" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveUserInfo">保存</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
</style>
