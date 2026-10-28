<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { authApi } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const activeTab = ref('password')

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
  pwdForm.old_password = ''
  pwdForm.new_password = ''
  pwdForm.confirm_password = ''
}

// 个人信息表单（预留）
const userInfo = reactive({
  username: auth.username || '',
  display_name: auth.displayName || '',
  email: '',
  phone: '',
})

function saveUserInfo() {
  ElMessage.info('个人信息功能待实现')
}
</script>

<template>
  <div>
    <el-card shadow="hover">
      <el-tabs v-model="activeTab">
        <!-- 修改密码页签 -->
        <el-tab-pane label="修改密码" name="password">
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

        <!-- 个人信息页签（预留） -->
        <el-tab-pane label="个人信息" name="info">
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
