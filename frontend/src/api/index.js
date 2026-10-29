import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// 请求拦截:自动带上 JWT
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截:统一错误处理 + 401 跳登录
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    const msg = error.response?.data?.detail || error.message || '请求失败'
    if (status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      localStorage.removeItem('login_info')
      if (location.hash !== '#/login') {
        location.hash = '#/login'
      }
    }
    // 428 = 密码已被重置,后端要求先改密。
    // 此时 MainLayout 已弹出不可关闭的改密窗口,这里不再重复弹错误提示,避免刷屏。
    if (status !== 428) {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

// ---- 认证 ----
export const authApi = {
  login: (data) => request.post('/auth/login', data),
  me: () => request.get('/auth/me'),
  register: (data) => request.post('/auth/register', data),
  changePassword: (data) => request.post('/auth/change-password', data),
  updateProfile: (data) => request.put('/auth/profile', data),
}

// ---- 项目 ----
export const projectApi = {
  list: () => request.get('/projects'),
  create: (data) => request.post('/projects', data),
  update: (id, data) => request.put(`/projects/${id}`, data),
  remove: (id) => request.delete(`/projects/${id}`),
  toggleStar: (id) => request.patch(`/projects/${id}/star`),
}

// ---- 测试用例 ----
export const testcaseApi = {
  list: (params) => request.get('/testcases', { params }),
  stats: (params) => request.get('/testcases/stats', { params }),
  create: (data) => request.post('/testcases', data),
  get: (id) => request.get(`/testcases/${id}`),
  update: (id, data) => request.put(`/testcases/${id}`, data),
  remove: (id) => request.delete(`/testcases/${id}`),
  submitReview: (id) => request.post(`/testcases/${id}/submit-review`),
  approve: (id, comment = '') => request.post(`/testcases/${id}/approve`, { comment }),
  reject: (id, comment) => request.post(`/testcases/${id}/reject`, { comment }),
}

// ---- 测试计划(版本/轮次) ----
export const planApi = {
  list: (params) => request.get('/plans', { params }),
  create: (data) => request.post('/plans', data),
  progress: (id) => request.get(`/plans/${id}/progress`),
  advance: (id, targetStage) => request.post(`/plans/${id}/advance`, targetStage ? { target_stage: targetStage } : {}),
  remove: (id) => request.delete(`/plans/${id}`),
  updateStageTimes: (id, data) => request.put(`/plans/${id}/stage-times`, data),
  countdown: (id, stage) => request.get(`/plans/${id}/countdown`, { params: stage ? { stage } : {} }),
  calendar: (params) => request.get('/plans/calendar', { params }),
}

// ---- 文件上传 ----
export const uploadApi = {
  // el-upload 用:返回上传地址
  imageUrl: '/api/uploads/image',
  // 手动上传图片,返回 { url, filename }
  image: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/uploads/image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

// ---- 用例导入 ----
export const importApi = {
  // 模板下载地址(带 token 需手动处理,这里返回 url 供 a 标签或 fetch 用)
  templateUrl: '/api/imports/template',
  importFile: (projectId, file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post(`/imports?project_id=${projectId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

// ---- 成员管理 ----
export const userApi = {
  list: () => request.get('/users'),
  listStaff: (params) => request.get('/users/staff', { params }),
  create: (data) => request.post('/users', data),
  update: (id, data) => request.put(`/users/${id}`, data),
  assignProjects: (id, projectIds) =>
    request.put(`/users/${id}/projects`, { project_ids: projectIds }),
  remove: (id) => request.delete(`/users/${id}`),
  resetPassword: (id) => request.post(`/users/${id}/reset-password`),
  myProjects: () => request.get('/users/me/projects'),
}

// ---- 测试报告 ----
export const reportApi = {
  exportPlan: (planId) => `/api/reports/plan/${planId}/export`,
  generate: (planId, stage) => request.post('/reports/generate', null, { params: { plan_id: planId, stage } }),
  list: (params) => request.get('/reports/list', { params }),
  get: (id) => request.get(`/reports/${id}`),
  exportGenerated: (id) => `/api/reports/${id}/export`,
  remove: (id) => request.delete(`/reports/${id}`),
}

// ---- 缺陷管理 ----
export const defectApi = {
  list: (params) => request.get('/defects', { params }),
  create: (data) => request.post('/defects', data),
  get: (id) => request.get(`/defects/${id}`),
  update: (id, data) => request.put(`/defects/${id}`, data),
  remove: (id) => request.delete(`/defects/${id}`),
  stats: (params) => request.get('/defects/stats/summary', { params }),
}

// ---- 通知 ----
export const notificationApi = {
  list: (params) => request.get('/notifications', { params }),
  unreadCount: () => request.get('/notifications/unread-count'),
  markRead: (data) => request.post('/notifications/mark-read', data),
  remove: (id) => request.delete(`/notifications/${id}`),
}

// ---- 用例版本 ----
export const versionApi = {
  list: (testcaseId) => request.get(`/testcases/${testcaseId}/versions`),
  get: (testcaseId, versionId) => request.get(`/testcases/${testcaseId}/versions/${versionId}`),
  rollback: (testcaseId, versionId) => request.post(`/testcases/${testcaseId}/versions/${versionId}/rollback`),
}

// ---- 自动化集成 ----
export const automationApi = {
  batchSubmit: (data) => request.post('/automation/batch', data),
  guide: () => request.get('/automation/guide'),
}

// ---- 需求管理 ----
export const requirementApi = {
  list: (params) => request.get('/requirements', { params }),
  create: (data) => request.post('/requirements', data),
  get: (id) => request.get(`/requirements/${id}`),
  update: (id, data) => request.put(`/requirements/${id}`, data),
  remove: (id) => request.delete(`/requirements/${id}`),
  linkTestcases: (id, testcaseIds) => request.post(`/requirements/${id}/testcases`, testcaseIds),
  unlinkTestcase: (reqId, tcId) => request.delete(`/requirements/${reqId}/testcases/${tcId}`),
  getTestcases: (id) => request.get(`/requirements/${id}/testcases`),
  coverageMatrix: (projectId) => request.get('/requirements/coverage/matrix', { params: { project_id: projectId } }),
}

// ---- 测试执行 ----
export const runApi = {
  create: (data) => request.post('/runs', data),
  list: (testcaseId, planId) =>
    request.get('/runs', { params: { testcase_id: testcaseId, plan_id: planId } }),
}

// ---- 团队管理 ----
export const teamApi = {
  list: () => request.get('/teams'),
  create: (data) => request.post('/teams', data),
  update: (id, data) => request.put(`/teams/${id}`, data),
  remove: (id) => request.delete(`/teams/${id}`),
  members: (id) => request.get(`/teams/${id}/members`),
  addMember: (id, data) => request.post(`/teams/${id}/members`, data),
  removeMember: (id, uid) => request.delete(`/teams/${id}/members/${uid}`),
  usersForSelect: () => request.get('/teams/users/list'),
}

// ---- 后台管理 ----
export const systemApi = {
  getConfig: () => request.get('/system/config'),
  updateConfig: (data) => request.put('/system/config', data),
}

// ---- 操作日志 ----
export const logApi = {
  list: (params) => request.get('/logs', { params }),
  actions: () => request.get('/logs/actions'),
}

// ---- 驾驶舱统计 ----
export const statsApi = {
  dashboard: (params) => request.get('/stats/dashboard', { params }),
  passRateTrends: (params) => request.get('/stats/trends/pass-rate', { params }),
  defectConvergence: (params) => request.get('/stats/trends/defect-convergence', { params }),
  workloadDistribution: (params) => request.get('/stats/workload/distribution', { params }),
}

// ---- P2: RBAC / 文件夹 / 标签 / 自定义字段 / 轮次 / 批量执行 ----
export const p2Api = {
  // RBAC 项目角色
  listRoles: (pid) => request.get(`/p2/roles/${pid}`),
  assignRole: (pid, data) => request.post(`/p2/roles/${pid}`, data),
  removeRole: (pid, userId) => request.delete(`/p2/roles/${pid}/${userId}`),

  // 文件夹
  listFolders: (pid) => request.get(`/p2/folders/${pid}`),
  createFolder: (data) => request.post('/p2/folders', data),
  updateFolder: (fid, data) => request.put(`/p2/folders/${fid}`, data),
  deleteFolder: (fid) => request.delete(`/p2/folders/${fid}`),
  moveTestcase: (tcid, folderId) => request.post(`/p2/testcases/${tcid}/move`, null, { params: { folder_id: folderId } }),

  // 标签
  listTags: (pid) => request.get(`/p2/tags/${pid}`),
  createTag: (data) => request.post('/p2/tags', data),
  deleteTag: (tagId) => request.delete(`/p2/tags/${tagId}`),
  assignTags: (tcid, tagIds) => request.post(`/p2/testcases/${tcid}/tags`, { tag_ids: tagIds }),
  getTestcaseTags: (tcid) => request.get(`/p2/testcases/${tcid}/tags`),

  // 自定义字段
  listCustomFields: (pid) => request.get(`/p2/custom-fields/${pid}`),
  createCustomField: (data) => request.post('/p2/custom-fields', data),
  deleteCustomField: (fieldId) => request.delete(`/p2/custom-fields/${fieldId}`),
  getTestcaseCustomFields: (tcid) => request.get(`/p2/testcases/${tcid}/custom-fields`),
  setTestcaseCustomFields: (tcid, values) => request.post(`/p2/testcases/${tcid}/custom-fields`, values),

  // 测试轮次
  listRounds: (planId) => request.get(`/p2/rounds/${planId}`),
  createRound: (data) => request.post('/p2/rounds', data),
  completeRound: (rid) => request.put(`/p2/rounds/${rid}/complete`),

  // 批量执行
  batchExecute: (data) => request.post('/p2/batch-execute', data),
}

// ---- 外部集成 ----
export const integrationApi = {
  // Webhook
  receiveWebhook: (data) => request.post('/integrations/webhook', data),
  
  // 缺陷同步
  syncDefect: (data) => request.post('/integrations/defect/sync', data),
  pushDefect: (defectId, targetSystem) => request.post(`/integrations/defect/push?target_system=${targetSystem}`, null),
  
  // 通知
  sendNotification: (data) => request.post('/integrations/notify', data),
  
  // 自动化测试
  reportAutomationResult: (data) => request.post('/integrations/automation/result', data),
  
  // CI/CD
  triggerPipeline: (data) => request.post('/integrations/cicd/trigger', data),
  
  // 配置管理
  listConfigs: () => request.get('/integrations/config/list'),
  createConfig: (data) => request.post('/integrations/config', data),
  updateConfig: (configId, data) => request.put(`/integrations/config/${configId}`, data),
  deleteConfig: (configId) => request.delete(`/integrations/config/${configId}`),
}

// ---- 测试用例导出(浏览器直接下载,需手动带 token) ----
export const testcaseExportUrl = (projectId) => `/api/testcases/export?project_id=${projectId}`

export default request
