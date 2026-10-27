import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import models  # noqa: F401  确保模型注册
from .config import settings
from .database import Base, engine
from .routers import auth, automation, defects, imports, logs, notifications, p2_features, plans, projects, requirements, reports, runs, stats, system, teams, testcases, uploads, users, versions
from .seed import seed_admin

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")


def migrate():
    """简单的内联迁移:create_all 不会 ALTER 已有表,这里手动补列"""
    # SQLite 不需要迁移，create_all 会创建完整表结构
    if settings.database_url.startswith("sqlite"):
        return
    
    with engine.connect() as conn:
        # testruns 补列
        for col, ddl in [
            ("plan_id", "ADD COLUMN plan_id INT NULL"),
            ("stage", "ADD COLUMN stage VARCHAR(8) NOT NULL DEFAULT 'SIT'"),
        ]:
            if not conn.execute(text(f"SHOW COLUMNS FROM testruns LIKE '{col}'")).fetchone():
                conn.execute(text(f"ALTER TABLE testruns {ddl}"))
        if not conn.execute(text("SHOW COLUMNS FROM testruns LIKE 'screenshot'")).fetchone():
            conn.execute(text("ALTER TABLE testruns ADD COLUMN screenshot VARCHAR(500) DEFAULT ''"))
        # users 补外包人员字段
        user_cols = [
            ("employee_no", "ADD COLUMN employee_no VARCHAR(64) DEFAULT ''"),
            ("category", "ADD COLUMN category VARCHAR(32) DEFAULT ''"),
            ("room", "ADD COLUMN room VARCHAR(64) DEFAULT ''"),
            ("group", "ADD COLUMN `group` VARCHAR(64) DEFAULT ''"),
            ("join_date", "ADD COLUMN join_date DATETIME NULL"),
            ("vendor", "ADD COLUMN vendor VARCHAR(128) DEFAULT ''"),
            ("system_name", "ADD COLUMN system_name VARCHAR(128) DEFAULT ''"),
            ("terminal_no", "ADD COLUMN terminal_no VARCHAR(64) DEFAULT ''"),
            ("employment_status", "ADD COLUMN employment_status VARCHAR(16) DEFAULT '在职'"),
            ("password_updated_at", "ADD COLUMN password_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("must_change_password", "ADD COLUMN must_change_password TINYINT(1) NOT NULL DEFAULT 0"),
        ]
        for col, ddl in user_cols:
            if not conn.execute(text(f"SHOW COLUMNS FROM users LIKE '{col}'")).fetchone():
                conn.execute(text(f"ALTER TABLE users {ddl}"))
        # system_config 补密码配置列
        for col, ddl in [
            ("password_expire_days", "ADD COLUMN password_expire_days INT DEFAULT 30"),
            ("password_remind_days", "ADD COLUMN password_remind_days INT DEFAULT 10"),
            ("default_sit_days", "ADD COLUMN default_sit_days INT DEFAULT 7"),
            ("default_uat_days", "ADD COLUMN default_uat_days INT DEFAULT 5"),
            ("default_pre_days", "ADD COLUMN default_pre_days INT DEFAULT 3"),
        ]:
            if not conn.execute(text(f"SHOW COLUMNS FROM system_config LIKE '{col}'")).fetchone():
                conn.execute(text(f"ALTER TABLE system_config {ddl}"))
        # testplans 补阶段时间列
        for col in ["sit_start", "sit_end", "uat_start", "uat_end", "pre_start", "pre_end"]:
            if not conn.execute(text(f"SHOW COLUMNS FROM testplans LIKE '{col}'")).fetchone():
                conn.execute(text(f"ALTER TABLE testplans ADD COLUMN {col} DATETIME NULL"))
        # projects 补新字段
        proj_cols = [
            ("project_no", "ADD COLUMN project_no VARCHAR(64) DEFAULT ''"),
            ("level", "ADD COLUMN level VARCHAR(32) DEFAULT ''"),
            ("project_type", "ADD COLUMN project_type VARCHAR(64) DEFAULT ''"),
            ("test_manager", "ADD COLUMN test_manager VARCHAR(64) DEFAULT ''"),
            ("tech_manager", "ADD COLUMN tech_manager VARCHAR(64) DEFAULT ''"),
            ("sa", "ADD COLUMN sa VARCHAR(64) DEFAULT ''"),
            ("is_key_project", "ADD COLUMN is_key_project TINYINT(1) DEFAULT 0"),
            ("is_started", "ADD COLUMN is_started TINYINT(1) DEFAULT 0"),
            ("starred", "ADD COLUMN starred TINYINT(1) DEFAULT 0"),
        ]
        for col, ddl in proj_cols:
            if not conn.execute(text(f"SHOW COLUMNS FROM projects LIKE '{col}'")).fetchone():
                conn.execute(text(f"ALTER TABLE projects {ddl}"))
        # testcases 补评审字段
        review_cols = [
            ("review_status", "ADD COLUMN review_status VARCHAR(16) DEFAULT '草稿'"),
            ("reviewer_id", "ADD COLUMN reviewer_id INT NULL"),
            ("review_comment", "ADD COLUMN review_comment TEXT"),
            ("reviewed_at", "ADD COLUMN reviewed_at DATETIME NULL"),
        ]
        for col, ddl in review_cols:
            if not conn.execute(text(f"SHOW COLUMNS FROM testcases LIKE '{col}'")).fetchone():
                conn.execute(text(f"ALTER TABLE testcases {ddl}"))
        # 创建需求表(如果不存在)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS requirements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                req_no VARCHAR(64) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                priority VARCHAR(8) DEFAULT '中',
                status VARCHAR(16) DEFAULT '待处理',
                created_by INT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_project_id (project_id),
                INDEX idx_req_no (req_no),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """))
        # 创建需求-用例关联表(如果不存在)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS requirement_testcases (
                requirement_id INT NOT NULL,
                testcase_id INT NOT NULL,
                PRIMARY KEY (requirement_id, testcase_id),
                FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
                FOREIGN KEY (testcase_id) REFERENCES testcases(id) ON DELETE CASCADE
            )
        """))
        # ===================== P2 迁移 =====================
        # testcases 补 folder_id
        if not conn.execute(text("SHOW COLUMNS FROM testcases LIKE 'folder_id'")).fetchone():
            conn.execute(text("ALTER TABLE testcases ADD COLUMN folder_id INT NULL"))
        # testruns 补 round_id
        if not conn.execute(text("SHOW COLUMNS FROM testruns LIKE 'round_id'")).fetchone():
            conn.execute(text("ALTER TABLE testruns ADD COLUMN round_id INT NULL"))
        # defects 补 run_id
        if not conn.execute(text("SHOW COLUMNS FROM defects LIKE 'run_id'")).fetchone():
            conn.execute(text("ALTER TABLE defects ADD COLUMN run_id INT NULL"))
        # 创建 P2 新表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_roles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                project_id INT NOT NULL,
                role VARCHAR(16) DEFAULT 'tester',
                INDEX idx_user_id (user_id),
                INDEX idx_project_id (project_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS testcase_folders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                parent_id INT NULL,
                name VARCHAR(128) NOT NULL,
                sort_order INT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_project_id (project_id),
                INDEX idx_parent_id (parent_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES testcase_folders(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS test_rounds (
                id INT AUTO_INCREMENT PRIMARY KEY,
                plan_id INT NOT NULL,
                name VARCHAR(64) NOT NULL,
                round_number INT DEFAULT 1,
                status VARCHAR(16) DEFAULT '进行中',
                created_by INT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_plan_id (plan_id),
                FOREIGN KEY (plan_id) REFERENCES testplans(id) ON DELETE CASCADE,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tags (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                name VARCHAR(64) NOT NULL,
                color VARCHAR(16) DEFAULT '#409EFF',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_project_id (project_id),
                INDEX idx_name (name),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS testcase_tags (
                testcase_id INT NOT NULL,
                tag_id INT NOT NULL,
                PRIMARY KEY (testcase_id, tag_id),
                FOREIGN KEY (testcase_id) REFERENCES testcases(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_fields (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_id INT NOT NULL,
                name VARCHAR(64) NOT NULL,
                field_type VARCHAR(16) DEFAULT 'text',
                options TEXT,
                required TINYINT(1) DEFAULT 0,
                sort_order INT DEFAULT 0,
                INDEX idx_project_id (project_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_field_values (
                id INT AUTO_INCREMENT PRIMARY KEY,
                field_id INT NOT NULL,
                testcase_id INT NOT NULL,
                value TEXT,
                INDEX idx_field_id (field_id),
                INDEX idx_testcase_id (testcase_id),
                FOREIGN KEY (field_id) REFERENCES custom_fields(id) ON DELETE CASCADE,
                FOREIGN KEY (testcase_id) REFERENCES testcases(id) ON DELETE CASCADE
            )
        """))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时:建表 + 迁移 + 初始化管理员
    Base.metadata.create_all(bind=engine)
    migrate()
    seed_admin()
    yield


app = FastAPI(
    title="测管平台 API",
    description="测试用例管理平台后端",
    version="0.2.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(plans.router)
app.include_router(testcases.router)
app.include_router(versions.router)
app.include_router(imports.router)
app.include_router(runs.router)
app.include_router(uploads.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(defects.router)
app.include_router(notifications.router)
app.include_router(automation.router)
app.include_router(requirements.router)
app.include_router(p2_features.router)
app.include_router(stats.router)
app.include_router(logs.router)
app.include_router(teams.router)
app.include_router(system.router)

os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ---------- 托管打包后的前端 (单服务部署) ----------
# 目录 backend/app/static 存放 `npm run build` 的产物。
# 前端用的是 hash 路由(#/xxx),因此不需要 SPA 的 history 回退规则,
# 直接静态托管即可。存在该目录时,打开 http://127.0.0.1:8000 就能用平台,无需 nginx。
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
HAS_FRONTEND = os.path.exists(os.path.join(STATIC_DIR, "index.html"))


@app.get("/")
def root():
    if HAS_FRONTEND:
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
    return {"name": "测管平台 API", "version": "0.2.0", "docs": "/docs",
            "hint": "未检测到前端产物,仅提供 API。把 npm run build 的 dist/* 放到 backend/app/static 即可单服务访问"}


if HAS_FRONTEND:
    # 必须放在所有 /api 路由之后:Starlette 按注册顺序匹配,先注册的先命中
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
