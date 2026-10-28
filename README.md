# 测管平台 (Test Case Management)

一个面向公司内部团队的**测试用例管理平台**,支持项目管理、用例管理、执行记录与统计。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 |
| 数据库 | MySQL 8.0 |
| 前端 | Vue 3 + Vite + Element Plus + Pinia + Vue Router |
| 鉴权 | JWT (Bearer Token) |

---

## 目录结构

```
D:\testmanage\
├── backend\                # 后端
│   ├── app\
│   │   ├── main.py         # FastAPI 入口
│   │   ├── config.py       # 配置(读取 .env)
│   │   ├── database.py     # SQLAlchemy 引擎/会话
│   │   ├── models.py       # 数据库模型
│   │   ├── schemas.py      # Pydantic 校验模型
│   │   ├── security.py     # 密码哈希 + JWT
│   │   ├── deps.py         # 鉴权依赖
│   │   ├── seed.py         # 初始化管理员
│   │   └── routers\        # 路由(auth/projects/testcases/runs)
│   ├── .env                # 环境变量(数据库连接、密钥)
│   └── requirements.txt
├── frontend\               # 前端
│   ├── src\
│   │   ├── api\index.js    # axios 封装 + 接口
│   │   ├── stores\auth.js  # 登录状态
│   │   ├── router\index.js # 路由 + 守卫
│   │   ├── layouts\        # 侧边栏布局
│   │   └── views\          # Login / Projects / TestCases
│   └── vite.config.js      # 含 /api 代理到后端
├── start-backend.bat       # 一键启动后端
└── start-frontend.bat      # 一键启动前端
```

---

## 启动方式

> MySQL 已在本机以 `C:\mysql` 免安装方式部署,登录后自动启动(开机自启已配置)。
> 若 MySQL 未运行,双击 `C:\mysql\start.bat` 即可。

### 1. 启动后端
双击 `D:\testmanage\start-backend.bat`,或在终端执行:
```
cd /d D:\testmanage\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
后端地址:`http://<服务器IP>:8000`
接口文档(Swagger):`http://<服务器IP>:8000/docs`

### 2. 启动前端
双击 `D:\testmanage\start-frontend.bat`,或:
```
cd /d D:\testmanage\frontend
npm run dev
```
前端地址:`http://<服务器IP>:5173`

### 3. 登录
浏览器打开 `http://<服务器IP>:5173`,使用默认账号:
- 用户名:`admin`
- 密码:`admin123`

---

## 默认账号与数据库信息

| 项 | 值 |
|----|----|
| 平台管理员 | admin / admin123 (首次登录后请修改密码) |
| MySQL root | 请在 `.env` 文件中配置 |
| 应用数据库 | 请在 `.env` 文件中配置 |
| 应用数据库用户 | 请在 `.env` 文件中配置 |
| MySQL 安装目录 | C:\mysql |
| MySQL 配置文件 | C:\mysql\my.ini |

> 安全提醒:
> 1. 首次登录后请尽快修改 admin 密码
> 2. 所有数据库凭据和密钥都应在 `backend/.env` 文件中配置,不要使用默认值
> 3. 参考 `backend/.env.example` 创建你的 `.env` 文件

---

## 功能清单 (MVP)

- [x] 登录 / JWT 鉴权
- [x] 项目管理(增删改查)
- [x] 测试用例管理(增删改查、分页、按项目/状态/优先级/关键字筛选)
- [x] 用例执行记录(通过/失败/阻塞 + 备注)
- [x] 执行历史查看
- [x] 用例统计(总数 + 按状态分布)

### 后续可扩展
- 测试计划(多用例组成测试任务,批量执行)
- 用例导入导出(Excel)
- 缺陷关联 / 对接 Jira
- 成员管理(目前可通过 `/docs` 调用 `POST /api/auth/register` 由 admin 添加成员)
- 测试报告导出

---

## 添加团队成员

当前 MVP 的成员管理仅开放了接口,管理员可在 Swagger 文档页(http://<服务器IP>:8000/docs)调用:
```
POST /api/auth/register
Body: { "username": "zhangsan", "password": "xxxxxx", "display_name": "张三" }
```
(需先点页面右上角 "Authorize" 填入登录拿到的 token)

---

## 常见问题

**Q: 重启电脑后 MySQL 没启动?**
A: 已配置登录自启。如未启动,双击 `C:\mysql\start.bat`。

**Q: 前端页面打不开 / 接口报错?**
A: 确认后端已启动(8000 端口)且 MySQL 已启动(3306 端口)。

**Q: 改了后端代码不生效?**
A: 后端用了 `--reload`,改完会自动重启;前端代码改完 Vite 会热更新。

**Q: 想改成生产部署?**
A: 前端 `npm run build` 生成 `dist/`,用 Nginx 托管静态文件并把 `/api` 反代到 8000;后端用 `uvicorn` 去掉 `--reload` 运行(建议用 systemd/容器做守护)。
