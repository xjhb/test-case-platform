<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { systemApi, authApi, notificationApi } from '../api'

const router = useRouter()
const auth = useAuthStore()
const unreadCount = ref(0)
let pollTimer = null

async function loadUnreadCount() {
  try {
    const res = await notificationApi.unreadCount()
    unreadCount.value = res.count || 0
  } catch (e) { /* ignore */ }
}

// ---- 无操作自动登出 ----
let idleTimer = null
const timeoutMinutes = ref(30)

function resetIdle() {
  if (idleTimer) clearTimeout(idleTimer)
  idleTimer = setTimeout(doIdleLogout, timeoutMinutes.value * 60 * 1000)
}

function doIdleLogout() {
  auth.logout()
  ElMessage.warning('长时间未操作,已自动退出登录')
  router.push({ name: 'login' })
}

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}

// ---- 修改密码 ----
const pwdVisible = ref(false)
const forcedPwd = ref(false)   // true = 管理员重置过密码,必须改密,弹窗不可关闭
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

function openChangePassword() {
  forcedPwd.value = false
  pwdForm.old_password = ''
  pwdForm.new_password = ''
  pwdForm.confirm_password = ''
  pwdVisible.value = true
}

// 管理员重置密码后的强制改密:独立一个不可关闭的对话框
function openForcedPassword() {
  pwdForm.old_password = ''
  pwdForm.new_password = ''
  pwdForm.confirm_password = ''
  forcedPwd.value = true
  pwdVisible.value = true
}

// 清掉本地的登录提示状态,避免刷新后重复强制改密
function clearForcedFlag() {
  try {
    const info = JSON.parse(localStorage.getItem('login_info') || '{}')
    info.must_change_password = false
    info.password_expired = false
    localStorage.setItem('login_info', JSON.stringify(info))
  } catch (e) {
    localStorage.removeItem('login_info')
  }
}

async function submitPassword() {
  await pwdFormRef.value.validate()
  await authApi.changePassword({
    old_password: pwdForm.old_password,
    new_password: pwdForm.new_password,
  })
  ElMessage.success('密码已修改')
  if (forcedPwd.value) {
    clearForcedFlag()
    forcedPwd.value = false
    // 重新加载,让各页面用新状态重新拉数据
    setTimeout(() => location.reload(), 600)
  }
  pwdVisible.value = false
}

// ---- 登录后密码状态提醒 ----
function checkPasswordExpiring() {
  const data = JSON.parse(localStorage.getItem('login_info') || '{}')
  // 管理员重置过密码:后端已拦截所有业务接口,这里必须强制改密
  if (data.must_change_password) {
    ElMessageBox.alert(
      '您的密码已被管理员重置,请立即修改密码后再继续使用系统。',
      '必须修改密码',
      {
        confirmButtonText: '立即修改',
        type: 'error',
        showClose: false,
        closeOnClickModal: false,
        closeOnPressEscape: false,
      }
    ).then(() => openForcedPassword())
    return
  }
  if (data.password_expired) {
    ElMessageBox.alert('您的密码已过期,请修改密码后继续使用', '密码已过期', {
      confirmButtonText: '去修改',
      type: 'error',
      showClose: false,
    }).then(() => openChangePassword())
  } else if (data.password_expiring) {
    ElMessageBox.alert(
      `您的密码将在 ${data.password_days_left} 天后到期,请尽快修改密码`,
      '密码即将到期',
      { confirmButtonText: '知道了', type: 'warning' }
    )
  }
}

onMounted(async () => {
  try {
    const cfg = await systemApi.getConfig()
    timeoutMinutes.value = cfg.session_timeout_minutes
  } catch (e) {
    // 获取配置失败用默认值
  }
  resetIdle()
  ;['mousemove', 'keydown', 'click', 'scroll'].forEach((evt) => {
    window.addEventListener(evt, resetIdle, { passive: true })
  })
  checkPasswordExpiring()
  loadUnreadCount()
  pollTimer = setInterval(loadUnreadCount, 60000)
})

onBeforeUnmount(() => {
  if (idleTimer) clearTimeout(idleTimer)
  if (pollTimer) clearInterval(pollTimer)
  ;['mousemove', 'keydown', 'click', 'scroll'].forEach((evt) => {
    window.removeEventListener(evt, resetIdle)
  })
})
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">测管平台</div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#001529"
        text-color="#c9d1d9"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>驾驶舱</span>
        </el-menu-item>
        <el-sub-menu index="func-test">
          <template #title>
            <el-icon><FolderOpened /></el-icon>
            <span>功能测试管理</span>
          </template>
          <el-menu-item index="/projects">
            <el-icon><Folder /></el-icon>
            <span>测试项目</span>
          </el-menu-item>
          <el-menu-item index="/plans">
            <el-icon><Tickets /></el-icon>
            <span>项目批次</span>
          </el-menu-item>
          <el-menu-item index="/calendar">
            <el-icon><Calendar /></el-icon>
            <span>测试日历</span>
          </el-menu-item>
          <el-menu-item index="/requirements">
            <el-icon><List /></el-icon>
            <span>需求管理</span>
          </el-menu-item>
          <el-menu-item index="/testcases">
            <el-icon><Document /></el-icon>
            <span>测试需求</span>
          </el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/defects">
          <el-icon><WarningFilled /></el-icon>
          <span>缺陷管理</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><DocumentChecked /></el-icon>
          <span>测试报告</span>
        </el-menu-item>
        <el-menu-item index="/automation">
          <el-icon><Connection /></el-icon>
          <span>自动化集成</span>
        </el-menu-item>
        <el-sub-menu v-if="auth.role === 'admin'" index="outsourcing">
          <template #title>
            <el-icon><UserFilled /></el-icon>
            <span>外包管理</span>
          </template>
          <el-menu-item index="/users">
            <el-icon><User /></el-icon>
            <span>外包人员管理</span>
          </el-menu-item>
          <el-menu-item index="/teams">
            <el-icon><UserFilled /></el-icon>
            <span>团队管理</span>
          </el-menu-item>
        </el-sub-menu>
        <el-menu-item v-if="auth.role === 'admin'" index="/logs">
          <el-icon><List /></el-icon>
          <span>操作日志</span>
        </el-menu-item>
        <el-sub-menu v-if="auth.role === 'admin'" index="settings">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>后台管理</span>
          </template>
          <el-menu-item index="/settings/timeout">
            <el-icon><Timer /></el-icon>
            <span>登录超时配置</span>
          </el-menu-item>
          <el-menu-item index="/settings/password">
            <el-icon><Lock /></el-icon>
            <span>密码到期配置</span>
          </el-menu-item>
          <el-menu-item index="/settings/stage">
            <el-icon><Calendar /></el-icon>
            <span>阶段时间配置</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="title">{{ $route.meta.title || '' }}</div>
        <div class="user">
          <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="notification-badge">
            <el-button text @click="router.push('/notifications')">
              <el-icon><Bell /></el-icon>
            </el-button>
          </el-badge>
          <el-tag v-if="auth.role === 'admin'" size="small" type="warning">管理员</el-tag>
          <span class="name">{{ auth.displayName }}</span>
          <el-button text type="warning" @click="openChangePassword">修改密码</el-button>
          <el-button text type="primary" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>

    </el-container>

    <!-- 修改密码对话框(放在container外) -->
    <!-- forcedPwd 时:不可关闭、无取消按钮,必须先改密 -->
    <el-dialog
      v-model="pwdVisible"
      :title="forcedPwd ? '必须修改密码' : '修改密码'"
      width="420px"
      :close-on-click-modal="false"
      :close-on-press-escape="!forcedPwd"
      :show-close="!forcedPwd"
    >
      <el-alert
        v-if="forcedPwd"
        type="error"
        :closable="false"
        show-icon
        title="密码已被管理员重置"
        description="修改密码成功前,系统其他功能不可使用。"
        style="margin-bottom: 16px"
      />
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入管理员提供的临时密码" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少6位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input v-model="pwdForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="!forcedPwd" @click="pwdVisible = false">取消</el-button>
        <el-button v-else @click="logout">退出登录</el-button>
        <el-button type="primary" @click="submitPassword">确认修改</el-button>
      </template>
    </el-dialog>
  </template>

<style scoped>
.layout {
  height: 100vh;
}
.aside {
  background: #001529;
}
.logo {
  height: 60px;
  color: #fff;
  font-size: 20px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 2px;
}
.header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #eee;
}
.header .title {
  font-size: 18px;
  font-weight: 600;
}
.header .user {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header .name {
  font-size: 14px;
  color: #606266;
}
.notification-badge {
  margin-right: 8px;
}
.notification-badge .el-badge__content {
  z-index: 10;
}
.main {
  background: #f0f2f5;
}
</style>
