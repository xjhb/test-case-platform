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
- [21. 我的待办 `/api/todo`](#21-我的待办)
- [22. 测试环境 `/api/environments`](#22-测试环境)
- [23. 阶段门禁 `/api/gates`](#23-阶段门禁)
- [24. 数据字典 `/api/dict`](#24-数据字典)
- [25. 项目模板 `/api/project-templates`](#25-项目模板)

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

### 创建项目时套用模板

`POST /api/projects` 额外接受 `template_id` 与三个阶段天数字段:

```json
{ "name": "核心系统改造", "project_no": "P2026-01", "template_id": 1,
  "default_sit_days": 12, "default_uat_days": 5, "default_pre_days": null }
```

- `template_id` 省略时使用标记为默认的模板;传 `0` 表示明确不套用任何模板;传不存在的 ID → `400 项目模板不存在`
- 模板里的门禁、自定义字段、标签、字典项按 [25. 项目模板](#25-项目模板) 的套用规则写入本项目
- 三个阶段天数取值范围 1-365,留空(`null`)表示跟随全局阶段配置;显式传入的天数覆盖模板天数

`PUT /api/projects/{id}` 支持 `"template_id": null`(或 `0`)解除模板来源记录,只清来源,不动已经套用到项目里的配置。
被项目记录的模板不允许删除,解除来源后才能删掉模板,历史项目的配置不受影响。

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
| POST | `/{id}/submit-review` | 提交评审,body 可传 `{"reviewer_id": 12}` 指定评审人(不传则通知测试负责人/项目经理) | 项目成员 |
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
| POST | `/{id}/advance` | 推进阶段(校验阶段门禁) | 项目成员;强制推进需 Admin |
| POST | `/{id}/complete` | 标记计划完成(校验当前阶段准出门禁) | 项目成员;强制完成需 Admin |
| POST | `/{id}/reopen` | 重新打开已完成计划 | 项目成员 |
| GET | `/{id}/cases` | 计划圈选的用例范围 | 项目成员 |
| POST | `/{id}/cases` | 圈选/追加/清空用例范围 | 项目成员 |
| PUT | `/{id}/stage-times` | 修改阶段时间 | 项目成员 |
| GET | `/{id}/countdown` | 阶段倒计时 | 项目成员 |
| DELETE | `/{id}` | 删除计划 | 项目成员 |

### 阶段说明

- **SIT**: 系统集成测试
- **UAT**: 用户验收测试
- **PRE**: 预发布测试

> `DELETE /{id}` 会级联清除该计划的执行记录、逐步结果、轮次和报告,
> 并把关联缺陷的 `plan_id` 置空;不会留下无法归属的孤儿数据。

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
  "screenshot": "/uploads/xxx.png",
  "env_id": 3
}
```

- `env_id` 可选,指定执行环境(见 [22. 测试环境](#22-测试环境));
  环境不存在、不属于计划所在项目或已停用 → `400`
- `GET /api/runs?testcase_id&plan_id&env_id` 支持按环境过滤,响应回显 `env_id`、`env_name`

---

## 7. 缺陷管理

**前缀**: `/api/defects`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 缺陷列表(分页/筛选) | 已登录 |
| POST | `` | 创建缺陷(初始状态固定为 `新建`) | 项目成员 |
| GET | `/status-flow` | 缺陷状态机流转表 | 已登录 |
| GET | `/stats/summary` | 缺陷统计 | 已登录 |
| GET | `/{id}` | 缺陷详情(含 `attachment_count`) | 项目成员 |
| PUT | `/{id}` | 更新缺陷(状态受状态机约束) | 项目成员 |
| DELETE | `/{id}` | 删除缺陷(级联清理附件记录与磁盘文件) | Admin |
| GET | `/{id}/traceability` | 缺陷来源追溯(用例/执行记录/计划) | 项目成员 |
| GET | `/{id}/attachments` | 附件列表(新→旧) | 项目成员 |
| POST | `/{id}/attachments` | 上传附件(multipart `file`) | 项目成员 |
| GET | `/attachments/{attId}/download` | 下载附件(RFC 5987 文件名) | 项目成员 |
| DELETE | `/attachments/{attId}` | 删除附件 | 上传者本人或 Admin |

### 缺陷状态机

状态集合: `新建` / `处理中` / `已修复` / `已验证` / `关闭` / `重新打开`

`GET /api/defects/status-flow` 返回的 `transitions` 为唯一事实来源,前端「流转」下拉按当前状态只渲染合法目标:

| 当前状态 | 允许流转到 |
|----------|------------|
| 新建 | 处理中、关闭 |
| 处理中 | 已修复、关闭 |
| 已修复 | 已验证、重新打开 |
| 已验证 | 关闭、重新打开 |
| 关闭 | 重新打开 |
| 重新打开 | 处理中、已修复、关闭 |

规则说明:

- 非法流转返回 `400`,响应 `detail` 会列出当前状态的可选目标,例如 `缺陷状态不能从 已修复 直接流转到 关闭,当前可选: 已验证, 重新打开`。
- `admin` 可强制流转到任意合法状态值(用于误操作纠正),普通成员只能按上表流转。
- 同状态提交视为无操作,直接放行。
- 时间戳维护: 进入 `已修复` 写 `resolved_at`;进入 `关闭` 写 `closed_at`;进入 `重新打开` 或退回 `处理中` 时清空 `resolved_at` 与 `closed_at`。
- 通知联动: `已修复` 时通知提单人验证,`重新打开` 时通知处理人;严重程度或优先级命中数据字典「计入紧急」标记的额外推送群机器人(见 24. 数据字典)。

### 缺陷附件

- 存储目录: `backend/app/uploads/defects/`,文件名重写为 `uuid.hex + 白名单扩展名`,原始文件名保存在数据库并在下载时还原。
- 单文件上限 20MB;扩展名白名单: `png/jpg/jpeg/gif/webp/txt/log/csv/json/xml/har/pdf/doc/docx/xls/xlsx/zip/rar/7z`,不在名单内或空文件返回 `400`。
- 图片附件的 `url` 字段为 `/uploads/defects/{存储名}`,可直接预览;其余文件走 `download` 接口以还原中文文件名。
- `can_delete` 由后端判定(仅上传者本人或 admin),前端据此显示删除按钮。
- 上传成功返回附件对象并写操作日志;删除附件会同时删除磁盘文件。

### 严重程度

`致命` / `严重` / `一般` / `提示`

优先级: `P0` / `P1` / `P2` / `P3`

> 以上为数据字典的内置默认取值，实际可配置项与「计入紧急」标记以 `GET /api/dict/options?dict_key=...` 为准（见 24. 数据字典）；
> 接口写入时按字典校验，创建缺陷未传 `severity` 时默认 `一般`。

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
| GET | `/list` | 报告列表(`project_id`/`plan_id` 筛选) | 已登录 |
| POST | `/generate` | 生成报告 | 项目成员 |
| GET | `/plan/{plan_id}/export` | 导出计划报告 Excel | 项目成员 |
| GET | `/plan/{plan_id}/export-pdf` | 导出计划报告 PDF | 项目成员 |
| GET | `/{id}` | 报告详情 | 项目成员 |
| GET | `/{id}/export` | 导出报告 Excel | 项目成员 |
| GET | `/{id}/export-pdf` | 导出报告 PDF | 项目成员 |
| DELETE | `/{id}` | 删除报告 | Admin |

> PDF 由后端 `reportlab` 直接生成(不依赖浏览器或 Office),中文字体内嵌,
> 收件方无需安装字体。版式与字体回退规则见 [导出格式说明](导出格式说明.md)。
> 两个导出接口都会写操作日志(`导出`),文件名按 RFC 5987 编码以支持中文版本名。

---

## 11. 通知

**前缀**: `/api/notifications`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 通知列表(分页/筛选,返回 `{total, items}`) | 已登录 |
| GET | `/unread-count` | 未读数量 | 已登录 |
| POST | `/mark-read` | 标记已读(传 `ids` 批量,不传则全部) | 已登录 |
| POST | `/scan-stage` | 立即扫描阶段到期提醒 | Admin |
| DELETE | `/{id}` | 删除通知 | 已登录 |

### GET /api/notifications (查询参数)

| 参数 | 类型 | 说明 |
|------|------|------|
| is_read | bool | 已读/未读筛选 |
| type | string | 通知类型(见下表) |
| page | int | 页码(默认1) |
| size | int | 每页条数(默认20,最大100) |

### 通知类型与触发点

| 类型 | 触发时机 | 收件人 | 跳转链接 |
|------|---------|--------|---------|
| `defect_assigned` | 新建/改派缺陷 | 被指派人(不通知操作人自己) | `/defects?focus={id}` |
| `defect_verify` | 缺陷置为「已修复」或「重新打开」 | 报告人 / 当前指派人 | `/defects?focus={id}` |
| `review_assigned` | 用例提交评审 | 指定评审人;未指定则项目上的测试负责人/项目经理 | `/testcases?project_id={pid}&focus={id}` |
| `review_result` | 用例评审通过或被驳回 | 用例创建人 | `/testcases?project_id={pid}&focus={id}` |
| `stage_expiring` | SIT/UAT/PRE 结束前 N 天,后端启动时及每 6 小时自动扫描 | 批次负责人 + 测试负责人/项目经理 | `/plans?project_id={pid}&focus={id}&stage={SIT}` |

> 站内信始终写入并随业务事务提交;邮件与群机器人属于外部通道,在后台线程尽力投递,
> 投递结果只记录到 `push_result` 字段,失败不影响业务接口。
> 只有 `broadcast=true` 的场景(缺陷严重程度或优先级命中数据字典「计入紧急」标记、阶段到期提醒)
> 才会推送到群机器人,避免群消息刷屏。
> 同一天同一计划的同一阶段只会产生一条到期提醒,可重复调用 `/scan-stage` 验证幂等。

`POST /api/notifications/scan-stage` 返回:

```json
{
  "remind_days": 3,
  "scanned_plans": 4,
  "created": 2,
  "skipped": 2,
  "message": "扫描 4 个进行中计划,新增 2 条到期提醒"
}
```

---

## 12. 成员管理

**前缀**: `/api/users`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 用户列表 | Admin |
| GET | `/options` | 在职成员下拉列表(id/username/display_name),供缺陷指派、用例评审选择 | 已登录 |
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
| stage_remind_days | 阶段结束前 N 天到期提醒,0 表示关闭 | 3 |

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

请求体 `items` 逐条写入执行记录;可选 `env_id` 把整批结果归属到某个测试环境
(须属于计划所在项目且未停用,否则 `400`),详见 [22. 测试环境](#22-测试环境)。

---

## 19. 外部集成

**前缀**: `/api/integrations`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/webhook` | 接收外部回调,原始事件先落库再处理 | 平台登录令牌,或配置 `WEBHOOK_SECRET` 后用 `X-Webhook-Token` |
| GET | `/webhook-events` | 最近回调事件与处理结果 | 已登录 |
| POST | `/defect/sync` | 外部缺陷 upsert 到本平台(外部系统+外部ID 为唯一键) | 已登录 |
| POST | `/defect/{id}/push` | 推送本平台缺陷到 Jira/禅道 建工单 | 已登录 |
| GET | `/defect/{id}/links` | 缺陷已关联的外部工单 | 已登录 |
| POST | `/notify` | 发送到 钉钉/企业微信/飞书/邮件 | 已登录 |
| POST | `/automation/result` | 上报单条自动化结果(含耗时) | 已登录 |
| POST | `/cicd/trigger` | 触发 Jenkins/GitLab CI/GitHub Actions | 已登录 |
| GET | `/status` | 各通道是否已配置凭据(只返回变量名,不返回值) | 已登录 |
| POST | `/self-test` | 通道连通性自检 | Admin |

> 集成凭据一律来自 `backend/.env` 或 Nacos,不提供在线录入。
> 未配置凭据的通道调用写接口返回 **503**,detail 中列出缺失的变量名;
> 远端不可达或返回错误返回 **502**。自检通道:邮件/CI/缺陷系统为只读探测,
> 钉钉/企业微信/飞书没有只读接口,自检会真实推送一条测试消息。

### 支持的外部系统

| 类型 | 系统 | 所需配置项 |
|------|------|-----------|
| 缺陷跟踪 | Jira | `JIRA_BASE_URL` `JIRA_USER` `JIRA_TOKEN` `JIRA_PROJECT_KEY` |
| 缺陷跟踪 | 禅道 | `ZENTAO_BASE_URL` `ZENTAO_ACCOUNT` `ZENTAO_PASSWORD` `ZENTAO_PRODUCT_ID` |
| 通知渠道 | 邮件 | `SMTP_HOST` `SMTP_USER` `SMTP_PASSWORD`(可选 `SMTP_PORT` `SMTP_FROM` `SMTP_SSL`) |
| 通知渠道 | 钉钉 | `DINGTALK_WEBHOOK_URL`(可选 `DINGTALK_SECRET` 加签) |
| 通知渠道 | 企业微信 | `WECOM_WEBHOOK_URL` |
| 通知渠道 | 飞书 | `FEISHU_WEBHOOK_URL` |
| CI/CD | Jenkins | `JENKINS_BASE_URL` `JENKINS_USER` `JENKINS_TOKEN` |
| CI/CD | GitLab CI | `GITLAB_BASE_URL` `GITLAB_TOKEN` |
| CI/CD | GitHub Actions | `GITHUB_TOKEN` |
| 回调鉴权 | - | `WEBHOOK_SECRET`(可选) |
| 通知开关 | - | `NOTIFY_EXTERNAL_ENABLED`(默认开;置 `0` 后站内信照常写入,不再调用邮件/群机器人) |
| 跳转拼接 | - | `PLATFORM_BASE_URL`(外部消息里的完整链接前缀,可选) |
| 自动化框架 | Selenium, Playwright, Cypress, JMeter | 通过 `/automation/result` 或 `/api/automation/batch` 回写 |

> `/status` 同时返回 `external_push_enabled`,前端「外部工具集成」页据此显示
> 「外部投递 已开启 / 已关闭(仅站内信)」。

---

## 20. 自动化集成

**前缀**: `/api/automation`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/batch` | 批量提交自动化结果 | 已登录 |
| POST | `/import-xml` | 导入 JUnit XML 执行结果 | 项目成员 |
| GET | `/guide` | 集成指南 | 已登录 |

> 回写前必须先把用例纳入计划范围(`测试计划 → 用例范围`),
> 未圈选的用例会计入返回的 `errors`,不会生成执行记录。
> 未圈选任何用例的历史计划按"项目全部用例"处理。

### POST /api/automation/batch

**请求体**:
```json
{
  "plan_id": 1,
  "stage": "SIT",
  "framework": "Selenium",
  "build_number": "123",
  "env_id": 3,
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

`env_id` 可选,写入本批全部执行记录;须属于计划所在项目且未停用,否则整批拒绝(`400`)。

---

### POST /api/automation/import-xml

`multipart/form-data` 导入 CI 产出的 JUnit XML(标准 `testsuites/testsuite/testcase` 结构)。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `files` | file[] | 是 | JUnit XML,单次最多 20 个,单个不超过 10MB |
| `plan_id` | int | 是 | 目标测试计划 |
| `stage` | string | 否 | SIT/UAT/PRE,默认 SIT |
| `framework` | string | 否 | 写入备注的框架名,缺省为 `JUnit` |
| `build_number` | string | 否 | CI 构建号,写入备注 `[Build#128]` |
| `env_id` | int | 否 | 执行环境 ID,须属于该计划所在项目且未停用 |
| `dry_run` | bool | 否 | true 时只解析与匹配,不落库 |

结果映射: `<failure>`/`<error>` → `失败`,`<skipped>` → `阻塞`,无子节点 → `通过`;
`time` 属性四舍五入写入 `duration_seconds`,失败信息写入 `remark`。

用例匹配规则(按顺序):
1. `testcase/@name` 与项目内用例标题做去空格、忽略大小写的精确匹配;
2. 名称中带平台编号时按 ID 匹配,支持 `TC-1024`、`case 1024`、`#1024` 等写法;
3. 命中后仍要求用例在计划圈选范围内,否则计入 `unmatched` 并给出原因。

**响应示例**:
```json
{
  "plan_id": 21, "stage": "SIT", "dry_run": false,
  "files": ["results.xml"], "total": 5, "matched": 3, "imported": 3,
  "by_status": {"通过": 1, "失败": 1, "阻塞": 1},
  "unmatched": [
    {"name": "XML导入探针不存在的用例", "classname": "com.demo.PayTest", "file": "results.xml", "status": "失败", "reason": "按用例标题和编号均未匹配到平台用例"},
    {"name": "用例#33", "file": "results.xml", "status": "通过", "testcase_id": 33, "reason": "用例#33 不属于计划#21的用例范围"}
  ],
  "unmatched_total": 2, "file_errors": [], "suites": [{"name": "登录模块", "tests": 3}]
}
```

> 每次导入都新增执行记录(与 `/batch` 一致,保留 Rerun 历史);
> 用例的 `status` 字段同步为该次导入的结果,与手工执行口径保持一致。
> 前端「自动化集成」页提供上传入口,可先「解析预览」确认匹配率再正式导入。

---

## 21. 我的待办

**前缀**: `/api/todo`

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/summary` | 当前用户的待办聚合 | 已登录 |

聚合的六类待办(全部只读,统计口径与各自模块一致):

| 字段 | 含义 | 判定条件 |
|------|------|---------|
| `review_cases` | 待我评审的用例 | `reviewer_id = 我` 且 评审状态为 评审中 |
| `rejected_cases` | 被驳回、需我修改的用例 | `created_by = 我` 且 评审状态为 已驳回 |
| `my_defects` | 指派给我的未修复缺陷 | `assignee_id = 我` 且 状态在 新建/处理中/重新打开 |
| `verify_defects` | 待我验证的缺陷 | `reporter_id = 我` 且 状态为 已修复 |
| `my_plans` | 我负责的批次进度 | 批次进行中且(我是创建人 或 我在该项目为 测试负责人/项目经理) |
| `pending_cases` | 负责批次当前阶段待执行用例 | 批次范围内还没有该阶段执行记录的用例 |

**响应示例**:
```json
{
  "review_cases": [{ "id": 77, "title": "...", "project_id": 1, "project_name": "test1", "priority": "P0", "submitted_at": "2026-11-05 09:40", "link": "/testcases?project_id=1&focus=77" }],
  "rejected_cases": [{ "id": 78, "title": "...", "comment": "预期结果缺失,请补充", "link": "/testcases?project_id=1&focus=78" }],
  "my_defects": [{ "id": 45, "title": "...", "severity": "致命", "status": "新建", "link": "/defects?focus=45" }],
  "verify_defects": [{ "id": 46, "title": "...", "resolved_at": "2026-11-05 09:40", "link": "/defects?focus=46" }],
  "my_plans": [{ "id": 20, "project_id": 1, "project_name": "test1", "version": "v1.0", "current_stage": "UAT", "stage_end": "2026-11-10 10:47", "remain_days": 5, "overdue": false, "total": 12, "pending": 3, "failed": 0, "link": "/plans?project_id=1&focus=20&stage=UAT" }],
  "pending_cases": [{ "id": 15, "title": "...", "plan_id": 7, "plan_version": "v1", "stage": "UAT", "priority": "P0", "link": "/plans?project_id=9&focus=7&stage=UAT" }],
  "unread_notifications": 3,
  "counts": { "review_cases": 1, "rejected_cases": 1, "my_defects": 1, "verify_defects": 1, "pending_cases": 8, "my_plans": 3 },
  "total": 12,
  "plan_scanned": false
}
```

> 每条待办都带 `link`,即前端路由的深链参数,点击后直接落到对应页面并展开详情。
> 数据按当前用户可访问的项目过滤,非所属项目的缺陷/用例不会出现在待办里。
> `counts` 是真实总数,列表每类最多返回 50 条;批次最多统计 20 个,
> 达到上限时 `plan_scanned = true`,前端会提示仅统计最近的批次。
> 待执行的判定与 `GET /api/plans/{id}/progress` 同源:以计划圈选范围(未圈选回退项目全部用例)
> 为分母,按该阶段最近一次执行结果是否为空计算。

---

## 22. 测试环境

**前缀**: `/api/environments`

环境按项目维护,执行记录(`testruns.env_id`)可归属到具体环境,用于按环境统计与执行追溯。

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 环境列表 `?project_id&stage&status` | 项目成员 |
| POST | `` | 新建环境 | 项目成员 |
| PUT | `/{id}` | 修改环境(项目不可变更) | 项目成员 |
| DELETE | `/{id}` | 删除环境(被执行记录引用时拒绝) | 项目成员 |
| GET | `/{id}/runs` | 环境下的执行记录 `?plan_id&page_size` | 项目成员 |

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `project_id` | int | 是 | 所属项目,新建后不可更改 |
| `name` | string | 是 | 环境名称,同项目内唯一 |
| `stage` | string | 否 | 主要阶段 `SIT`/`UAT`/`PRE`,默认 SIT |
| `status` | string | 否 | `可用`/`占用中`/`维护中`/`已停用`,默认 可用 |
| `url` | string | 否 | 访问地址,如 `http://<your-server>:8080/core` |
| `version` | string | 否 | 部署版本 |
| `owner_id` | int | 否 | 负责人用户 ID,须为在职成员 |
| `remark` | string | 否 | 备注 |

列表与详情额外返回 `owner_name`、`run_count`(该环境执行记录数)、
`failed_count`(其中状态为失败或阻塞的条数)。

### 约束

- 阶段、状态取值非法 → `400 阶段只能是: SIT / UAT / PRE`
- 同项目重名 → `400 该项目下环境名称已存在`
- 执行时指定的环境不存在、不属于计划所在项目、或状态为 `已停用` → `400`
- 已被执行记录引用的环境不能删除 →
  `400 该环境已被 3 条执行记录引用,请改为「已停用」而不是删除,以保留执行追溯链`
- 环境记录 `执行`/`新增`/`编辑`/`删除` 操作日志,执行日志的 detail 中带 `环境:<名称>`

---

## 23. 阶段门禁

**前缀**: `/api/gates`

按项目配置阶段准入/准出规则。推进阶段时校验「当前阶段准出 + 目标阶段准入」,
标记完成时校验「当前阶段准出」;未配置规则表示不限制。

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/rules` | 规则目录(前端渲染配置项) | 已登录 |
| GET | `` | 项目门禁列表 `?project_id&stage&kind` | 项目成员 |
| POST | `` | 新建门禁规则 | 项目成员 |
| PUT | `/{id}` | 修改阈值/阶段/类型/启停 | 项目成员 |
| DELETE | `/{id}` | 删除门禁规则 | 项目成员 |
| GET | `/check` | 校验计划门禁 `?plan_id&stage&kind` | 项目成员 |

### 规则清单

| key | 含义 | 方向 |
|-----|------|------|
| `case_total_min` | 纳入用例数不少于(条) | `>=` |
| `executed_rate_min` | 执行率不低于(%) | `>=` |
| `pass_rate_min` | 通过率不低于(%) | `>=` |
| `failed_max` | 失败用例不超过(条) | `<=` |
| `blocked_max` | 阻塞用例不超过(条) | `<=` |
| `pending_max` | 未执行用例不超过(条) | `<=` |
| `review_approved_min` | 评审通过率不低于(%) | `>=` |
| `open_defects_max` | 未关闭缺陷不超过(个) | `<=` |
| `open_critical_defects_max` | 未关闭紧急缺陷不超过(个)；紧急口径由字典 `defect_severity` 的「计入紧急」项决定 | `<=` |

指标口径与 `GET /api/plans/{id}/progress` 完全一致:分母是计划圈选的用例(未圈选回退项目全部用例),
执行结果取该阶段每条用例的最近一次记录;缺陷统计覆盖本计划或本范围内用例。

### POST /api/plans/{id}/advance

**请求体**:
```json
{ "target_stage": "UAT", "force": false, "reason": "" }
```

- 门禁未达标且 `force=false` → `400 门禁未达标:[UAT·准入] 通过率不低于 >= 95%,实际 66.7%`
- 门禁未达标且 `force=true`:非管理员 → `403`;`reason` 为空 → `400`
- 强制推进成功时 `forced=true`,操作日志记录未达标明细与理由

**响应**:
```json
{ "id": 30, "current_stage": "UAT", "status": "进行中", "forced": true,
  "gate": { "passed": false, "failures": "[SIT·准出] 通过率不低于 >= 100%,实际 66.7%" } }
```

### POST /api/plans/{id}/complete

请求体同上(只需 `force`/`reason`),按当前阶段准出校验;`/{id}/reopen` 把已完成计划退回进行中并留痕。

---

## 24. 数据字典

**前缀**: `/api/dict`

字典**类型**由代码固定,字典**取值**在后台可维护,用来替代原先散落在前后端的硬编码枚举。
取值分两层:`project_id` 为空是全局默认项(仅管理员维护),项目下同名 `label` 的项覆盖全局项
(包括把 `enabled=false` 用来隐藏某个内置项)。内置默认项永远作为兜底,删不掉也改不了名。

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/types` | 类型目录:`configurable` 可维护 + `locked` 固定口径及原因 | 已登录 |
| GET | `/options` | 单个类型的启用项 `?dict_key&project_id`(下拉框取值) | 项目成员 |
| GET | `/effective` | 一次取回全部类型有效项 `?project_id`(省略则按全局口径,前端缓存 60s) | 项目成员 |
| GET | `` | 配置页视图 `?dict_key&project_id`,含停用项与来源标记 | 项目成员 |
| POST | `` | 新增选项 | 全局=Admin;项目=Tester+ |
| PUT | `/{item_id}` | 改名/色值/排序/启停/计入紧急 | 全局=Admin;项目=Tester+ |
| DELETE | `/{item_id}` | 删除自定义选项(内置项返回 400) | 全局=Admin;项目=Tester+ |

### 可维护类型

| key | 名称 | mode | 计入紧急 | 内置默认项 |
|-----|------|------|----------|------------|
| `case_priority` | 用例优先级 | validate | 是 | P0 / P1 / P2 / P3 |
| `case_module` | 用例模块 | suggest | 否 | 登录 / 交易 / 退款 / 报表 |
| `defect_severity` | 缺陷严重程度 | validate | 是 | 致命 / 严重 / 一般 / 提示 |
| `defect_priority` | 缺陷优先级 | validate | 是 | P0 / P1 / P2 / P3 |
| `requirement_priority` | 需求优先级 | validate | 否 | 高 / 中 / 低 |

`mode=validate` 的写入(新建/编辑用例、需求、缺陷)会校验取值,非法值报
`400 优先级只能是: P0、P1、P2、P3`;历史数据里已存在的旧值靠 `current=` 逃生,不至于改一条记录就被拦下。
`mode=suggest` 只做提示不做拦截(模块名允许自由填写)。
`is_urgent` 取代了原先写死的"致命/严重/P0/P1"集合,哪些算紧急由字典项决定,影响缺陷列表的紧急标记、通知广播与门禁统计。
`case_priority` 中排序最前的启用项即统计口径里的「最高优先级」,数据看板的严重缺陷占比按它取分母,不再写死 `P0`。

### 固定口径(只读)

| key | 名称 | 不能配置的原因 |
|-----|------|----------------|
| `stage` | 测试阶段 SIT/UAT/PRE | 阶段推进、门禁规则、报告分阶段统计均按此固定顺序取数 |
| `run_status` | 执行结果 未执行/通过/失败/阻塞 | 通过率、执行率与准出门禁直接按这几个值聚合 |
| `review_status` | 用例评审状态 | 评审计数与「已批准」门禁条件依赖固定状态串 |
| `defect_status` | 缺陷状态 | 缺陷状态机与待办、通知路由依赖这组状态及其流转关系 |

### 示例

```http
POST /api/dict
{ "dict_key": "case_priority", "project_id": 3, "label": "P0-冒烟", "color": "danger",
  "sort_order": 0, "is_urgent": true, "remark": "核心链路" }
```

```json
// GET /api/dict/effective?project_id=3  (节选)
{ "case_priority": [
    { "id": null, "label": "P0", "color": "danger", "sort_order": 1,
      "enabled": true, "is_urgent": true, "builtin": true, "source": "default" },
    { "id": 81, "label": "P0-冒烟", "color": "danger", "sort_order": 0,
      "enabled": true, "is_urgent": true, "builtin": false, "source": "project" } ] }
```

`GET /api/dict` 与 `/effective` 的读取范围只有「全局行 + 本项目行」,不会把其他项目的自定义项串过来;
传 `project_id` 时要求是该项目的成员。

---

## 25. 项目模板

**前缀**: `/api/project-templates`

一个模板打包五类配置:阶段天数 `stage_days`、门禁规则 `gates`、自定义字段 `custom_fields`、
标签 `tags`、字典项 `dict_items`。新建项目时选择模板即自动套用,已有项目也可手动套用。

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `` | 模板列表(默认模板排最前) | 已登录 |
| POST | `` | 新建模板 | Admin |
| PUT | `/{id}` | 编辑模板 | Admin |
| DELETE | `/{id}` | 删除模板 | Admin |
| POST | `/{id}/apply?project_id=` | 套用到已有项目 | 该项目 Tester+ |
| GET | `/collect/{project_id}` | 把现有项目配置导出成模板草稿 | 该项目成员 |

### 套用是幂等的

`apply` 按签名去重,重复套用不会堆叠配置,只补齐缺少的部分;响应返回各项写入条数与跳过条数:

```json
{ "template_id": 1, "project_id": 3, "stage_days": 1, "gates": 2, "custom_fields": 0,
  "tags": 1, "dict_items": 3, "skipped": 4 }
```

去重签名:门禁按 `(stage, kind, rule)`,自定义字段按名称,标签按名称,字典项按 `(dict_key, label)`;
阶段天数只在项目当前值与模板不同时才写。套进来的字典项落在**该项目**的 `dict_items` 行(`builtin=false`),
不影响全局默认项。

### 校验与来源记录

- `stage_days` 的 key 只能是 `SIT/UAT/PRE`,值为 1-365 的整数
- `gates` 的 `stage/kind/rule` 必须在门禁规则目录内,阈值不能为负
- `dict_items` 的 `dict_key` 必须是已登记的字典类型,`label` 不能为空
- 模板名称唯一;`is_default=true` 的模板全库只有一个,设置新默认会自动取消旧的
- `projects.template_id` 记录来源。被引用的模板不允许删除,先 `PUT /api/projects/{id} {"template_id": 0}` 解除来源
- 默认模板被删除时,剩余模板中 ID 最小的自动接位;服务启动时若发现没有任何默认模板也会补上,避免新建项目失去默认套用来源

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
