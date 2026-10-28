# 测管平台 API 接口文档

> 基础地址: `http://<your-server>:8000`
> 认证方式: Bearer Token (登录后获取)
> 接口文档(运行时): `http://<your-server>:8000/docs`

---

## 目录

- [1. 认证模块 `/api/auth`](#1-认证模块)
- [2. 项目管理 `/api/projects`](#2-项目管理)
- [3. 测试用例 `/api/testcases`](#3-测试用例)
- [4. 用例版本 `/api/testcases/{id}/versions`](#4-用例版本)
- [5. 测试计划 `/api/plans`](#5-测试计划)
- [6. 测试执行 `/api/runs`](#6-测试执行)
- [7. 缺陷管理 `/api/defects`](#7-缺陷管理)
- [8. 需求管理 `/api/requirements`](#8-需求管理)
- [9. 统计看板 `/api/stats`](#9-统计看板)
- [10. 测试报告 `/api/reports`](#10-测试报告)
- [11. 通知 `/api/notifications`](#11-通知)
- [12. 成员管理 `/api/users`](#12-成员管理)
- [13. 团队管理 `/api/teams`](#13-团队管理)
- [14. 操作日志 `/api/logs`](#14-操作日志)
- [15. 系统配置 `/api/system`](#15-系统配置)
- [16. 文件上传 `/api/uploads`](#16-文件上传)
- [17. 用例导入 `/api/imports`](#17-用例导入)
- [18. P2 功能 `/api/p2`](#18-p2-功能)
- [19. 外部集成 `/api/integrations`](#19-外部集成)
- [20. 自动化集成 `/api/automation`](#20-自动化集成)

---

## 1. 认证模块

**前缀**: `/api/auth`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/login` | 用户登录，返回 JWT Token | 公开 |
| GET | `/me` | 获取当前登录用户信息 | 已登录 |
| POST | `/change-password` | 修改密码 | 已登录 |
| POST | `/register` | 注册新用户 | Admin |

### POST /api/auth/login

**请求体**:
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**响应**:
```json
{
  "access_token": "eyJ...",
  "role": "admin",
  "display_name": "管理员",
  "must_change_password": false,
  "password_expiring": false,
  "password_days_left": 30,
  "password_expired": false
}
```

---

## 2. 项目管理

**前缀**: `/api/projects`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 获取项目列表 | 已登录 |
| POST | `` | 创建项目 | Admin |
| GET | `/{id}` | 获取项目详情 | 项目成员 |
| PUT | `/{id}` | 更新项目 | Admin |
| PATCH | `/{id}/star` | 切换关注星标 | 项目成员 |
| DELETE | `/{id}` | 删除项目 | Admin |

---

## 3. 测试用例

**前缀**: `/api/testcases`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 用例列表(分页/筛选) | 已登录 |
| POST | `` | 创建用例 | 项目成员 |
| GET | `/export` | 导出用例 Excel | 项目成员 |
| GET | `/stats` | 用例统计 | 已登录 |
| GET | `/{id}` | 用例详情 | 项目成员 |
| PUT | `/{id}` | 更新用例 | 项目成员 |
| DELETE | `/{id}` | 删除用例 | 项目成员 |
| POST | `/{id}/submit-review` | 提交评审 | 项目成员 |
| POST | `/{id}/approve` | 批准用例 | 项目成员 |
| POST | `/{id}/reject` | 驳回用例 | 项目成员 |

### GET /api/testcases (查询参数)

| 参数 | 类型 | 说明 |
|------|------|------|
| project_id | int | 项目ID |
| plan_id | int | 计划ID |
| stage | string | 阶段(SIT/UAT/PRE) |
| status | string | 执行状态 |
| priority | string | 优先级(P0/P1/P2/P3) |
| review_status | string | 评审状态 |
| keyword | string | 关键字搜索 |
| all_stages | bool | 返回三阶段状态 |
| page | int | 页码(默认1) |
| page_size | int | 每页条数(默认20) |

---

## 4. 用例版本

**前缀**: `/api/testcases/{testcase_id}/versions`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 版本列表 | 项目成员 |
| GET | `/{version_id}` | 版本详情 | 项目成员 |
| POST | `/{version_id}/rollback` | 回滚到指定版本 | 项目成员 |

---

## 5. 测试计划

**前缀**: `/api/plans`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 计划列表 | 已登录 |
| POST | `` | 创建计划 | 项目成员 |
| GET | `/calendar` | 日历视图 | 已登录 |
| GET | `/{id}/progress` | 计划进度 | 项目成员 |
| POST | `/{id}/advance` | 推进阶段 | 项目成员 |
| PUT | `/{id}/stage-times` | 修改阶段时间 | 项目成员 |
| GET | `/{id}/countdown` | 阶段倒计时 | 项目成员 |
| DELETE | `/{id}` | 删除计划 | 项目成员 |

### 阶段说明

- **SIT**: 系统集成测试
- **UAT**: 用户验收测试
- **PRE**: 预发布测试

---

## 6. 测试执行

**前缀**: `/api/runs`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `` | 创建执行记录 | 项目成员 |
| GET | `` | 执行记录列表 | 项目成员 |

### POST /api/runs

**请求体**:
```json
{
  "testcase_id": 1,
  "plan_id": 1,
  "stage": "SIT",
  "status": "通过",
  "remark": "执行通过",
  "screenshot": "/uploads/xxx.png"
}
```

---

## 7. 缺陷管理

**前缀**: `/api/defects`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 缺陷列表(分页/筛选) | 已登录 |
| POST | `` | 创建缺陷 | 项目成员 |
| GET | `/stats/summary` | 缺陷统计 | 已登录 |
| GET | `/{id}` | 缺陷详情 | 项目成员 |
| PUT | `/{id}` | 更新缺陷 | 项目成员 |
| DELETE | `/{id}` | 删除缺陷 | Admin |

### 缺陷状态

`新建` → `处理中` → `已修复` → `已验证` → `关闭`

### 严重程度

`致命` / `严重` / `一般` / `提示`

---

## 8. 需求管理

**前缀**: `/api/requirements`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 需求列表 | 已登录 |
| POST | `` | 创建需求 | 项目成员 |
| GET | `/coverage/matrix` | 需求覆盖率矩阵 | 项目成员 |
| GET | `/{id}` | 需求详情 | 项目成员 |
| PUT | `/{id}` | 更新需求 | 项目成员 |
| DELETE | `/{id}` | 删除需求 | 项目成员 |
| POST | `/{id}/testcases` | 关联测试用例 | 项目成员 |
| GET | `/{id}/testcases` | 获取关联用例 | 项目成员 |
| DELETE | `/{id}/testcases/{tcid}` | 取消关联 | 项目成员 |

---

## 9. 统计看板

**前缀**: `/api/stats`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/dashboard` | 数据看板总览 | 已登录 |
| GET | `/trends/pass-rate` | 通过率趋势 | 已登录 |
| GET | `/trends/defect-convergence` | 缺陷收敛曲线 | 已登录 |
| GET | `/workload/distribution` | 人员工作量分布 | 已登录 |

---

## 10. 测试报告

**前缀**: `/api/reports`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/list` | 报告列表 | 已登录 |
| POST | `/generate` | 生成报告 | 项目成员 |
| GET | `/plan/{plan_id}/export` | 导出计划报告 Excel | 项目成员 |
| GET | `/{id}` | 报告详情 | 项目成员 |
| GET | `/{id}/export` | 导出报告 Excel | 项目成员 |
| DELETE | `/{id}` | 删除报告 | Admin |

---

## 11. 通知

**前缀**: `/api/notifications`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 通知列表 | 已登录 |
| GET | `/unread-count` | 未读数量 | 已登录 |
| POST | `/mark-read` | 标记已读 | 已登录 |
| DELETE | `/{id}` | 删除通知 | 已登录 |

---

## 12. 成员管理

**前缀**: `/api/users`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 用户列表 | Admin |
| GET | `/staff` | 外包人员列表 | Admin |
| GET | `/me/projects` | 我的项目 | 已登录 |
| POST | `` | 创建用户 | Admin |
| PUT | `/{id}` | 更新用户 | Admin |
| PUT | `/{id}/projects` | 分配项目 | Admin |
| POST | `/{id}/reset-password` | 重置密码 | Admin |
| DELETE | `/{id}` | 删除用户 | Admin |

---

## 13. 团队管理

**前缀**: `/api/teams`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 团队列表 | 已登录 |
| POST | `` | 创建团队 | Admin |
| PUT | `/{id}` | 更新团队 | Admin |
| DELETE | `/{id}` | 删除团队 | Admin |
| GET | `/{id}/members` | 团队成员列表 | 已登录 |
| POST | `/{id}/members` | 添加成员 | Admin |
| DELETE | `/{id}/members/{uid}` | 移除成员 | Admin |
| GET | `/users/list` | 可选用户列表 | Admin |

---

## 14. 操作日志

**前缀**: `/api/logs`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 日志列表(分页/筛选) | Admin |
| GET | `/actions` | 操作类型列表 | Admin |

---

## 15. 系统配置

**前缀**: `/api/system`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/config` | 获取系统配置 | 已登录 |
| PUT | `/config` | 更新系统配置 | Admin |

### 配置项

| 字段 | 说明 | 默认值 |
|------|------|--------|
| session_timeout_minutes | 登录超时(分钟) | 30 |
| password_expire_days | 密码有效期(天) | 30 |
| password_remind_days | 密码到期提醒(天) | 10 |
| default_sit_days | SIT 默认天数 | 7 |
| default_uat_days | UAT 默认天数 | 5 |
| default_pre_days | PRE 默认天数 | 3 |

---

## 16. 文件上传

**前缀**: `/api/uploads`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/image` | 上传图片 | 已登录 |

**支持格式**: png, jpg, jpeg, gif, webp
**大小限制**: 10MB

---

## 17. 用例导入

**前缀**: `/api/imports`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/template` | 下载导入模板 | 已登录 |
| POST | `` | 导入用例 | 项目成员 |

**支持格式**: xlsx, csv

---

## 18. P2 功能

**前缀**: `/api/p2`

### RBAC 项目角色

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/roles/{project_id}` | 项目角色列表 | 项目成员 |
| POST | `/roles/{project_id}` | 分配角色 | 项目管理 |
| DELETE | `/roles/{project_id}/{user_id}` | 移除角色 | 项目管理 |

**角色类型**: `manager` / `test_lead` / `tester` / `viewer`

### 用例目录树

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/folders/{project_id}` | 文件夹树 | 项目成员 |
| POST | `/folders` | 创建文件夹 | 可编辑 |
| PUT | `/folders/{id}` | 更新文件夹 | 可编辑 |
| DELETE | `/folders/{id}` | 删除文件夹 | 可编辑 |
| POST | `/testcases/{id}/move` | 移动用例到文件夹 | 可编辑 |

### 标签

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/tags/{project_id}` | 标签列表 | 项目成员 |
| POST | `/tags` | 创建标签 | 可编辑 |
| DELETE | `/tags/{id}` | 删除标签 | 可编辑 |
| POST | `/testcases/{id}/tags` | 分配标签 | 可编辑 |
| GET | `/testcases/{id}/tags` | 用例标签 | 项目成员 |

### 自定义字段

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/custom-fields/{project_id}` | 字段列表 | 项目成员 |
| POST | `/custom-fields` | 创建字段 | 项目管理 |
| DELETE | `/custom-fields/{id}` | 删除字段 | 项目管理 |
| GET | `/testcases/{id}/custom-fields` | 用例字段值 | 项目成员 |
| POST | `/testcases/{id}/custom-fields` | 设置字段值 | 可编辑 |

### 测试轮次

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/rounds/{plan_id}` | 轮次列表 | 项目成员 |
| POST | `/rounds` | 创建轮次 | 项目管理 |
| PUT | `/rounds/{id}/complete` | 完成轮次 | 项目管理 |

### 批量执行

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/batch-execute` | 批量执行用例 | 可编辑 |

---

## 19. 外部集成

**前缀**: `/api/integrations`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/webhook` | 通用 Webhook 接收 | 已登录 |
| POST | `/defect/sync` | 同步外部缺陷 | 已登录 |
| POST | `/defect/push` | 推送缺陷到外部 | 已登录 |
| POST | `/notify` | 发送通知 | 已登录 |
| POST | `/automation/result` | 上报自动化结果 | 已登录 |
| POST | `/cicd/trigger` | 触发 CI/CD | 已登录 |
| GET | `/config/list` | 集成配置列表 | 已登录 |
| POST | `/config` | 创建集成配置 | Admin |
| PUT | `/config/{id}` | 更新集成配置 | Admin |
| DELETE | `/config/{id}` | 删除集成配置 | Admin |

### 支持的外部系统

| 类型 | 系统 |
|------|------|
| 缺陷跟踪 | Jira, 禅道 |
| 通知渠道 | 钉钉, 企业微信, 飞书, 邮件 |
| CI/CD | Jenkins, GitLab CI, GitHub Actions |
| 自动化框架 | Selenium, Playwright, Cypress, JMeter |
| 代码仓库 | GitLab, GitHub |

---

## 20. 自动化集成

**前缀**: `/api/automation`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/batch` | 批量提交自动化结果 | 已登录 |
| GET | `/guide` | 集成指南 | 已登录 |

### POST /api/automation/batch

**请求体**:
```json
{
  "plan_id": 1,
  "stage": "SIT",
  "framework": "Selenium",
  "build_number": "123",
  "results": [
    {
      "testcase_id": 10,
      "status": "通过",
      "remark": "自动化测试通过",
      "screenshot": "https://example.com/screenshot.png",
      "duration_seconds": 5
    }
  ]
}
```

---

## 通用说明

### 认证

所有需要认证的接口需在请求头中携带 Token:

```
Authorization: Bearer <access_token>
```

### 错误响应

```json
{
  "detail": "错误描述"
}
```

### 分页响应

```json
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "items": [...]
}
```

### 权限说明

| 角色 | 说明 |
|------|------|
| admin | 管理员，所有权限 |
| member | 普通成员，受项目权限控制 |
| manager | 项目管理角色 |
| test_lead | 测试负责人角色 |
| tester | 测试执行角色 |
| viewer | 只读角色 |
