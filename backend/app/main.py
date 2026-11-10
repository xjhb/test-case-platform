import os
import sys

# Windows 下 stdout 默认 GBK: 中文日志会变成乱码字节, emoji 会直接抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import models  # noqa: F401  确保模型注册
from .config import settings
from .database import Base, engine
from .notify import start_stage_scheduler
from .routers import auth, automation, data_dict, defects, environments, gates, imports, integrations, lineage, logs, notifications, p2_features, plans, projects, requirements, reports, runs, stats, system, teams, templates, testcases, todo, uploads, users, versions
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
        # testruns 补自动化执行耗时
        if not conn.execute(text("SHOW COLUMNS FROM testruns LIKE 'duration_seconds'")).fetchone():
            conn.execute(text("ALTER TABLE testruns ADD COLUMN duration_seconds INT NULL"))
        # testruns 补执行环境
        if not conn.execute(text("SHOW COLUMNS FROM testruns LIKE 'env_id'")).fetchone():
            conn.execute(text("ALTER TABLE testruns ADD COLUMN env_id INT NULL"))
        # defects 补 run_id
        if not conn.execute(text("SHOW COLUMNS FROM defects LIKE 'run_id'")).fetchone():
            conn.execute(text("ALTER TABLE defects ADD COLUMN run_id INT NULL"))
        # notifications 补外部通道投递结果
        if not conn.execute(text("SHOW COLUMNS FROM notifications LIKE 'push_result'")).fetchone():
            conn.execute(text("ALTER TABLE notifications ADD COLUMN push_result VARCHAR(255) DEFAULT ''"))
        # system_config 补阶段到期提醒天数
        if not conn.execute(text("SHOW COLUMNS FROM system_config LIKE 'stage_remind_days'")).fetchone():
            conn.execute(text("ALTER TABLE system_config ADD COLUMN stage_remind_days INT DEFAULT 3"))
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
        # ===================== P2-3: 数据字典 + 项目模板 =====================
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dict_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                dict_key VARCHAR(32) NOT NULL,
                project_id INT NULL,
                label VARCHAR(64) NOT NULL,
                color VARCHAR(16) DEFAULT '',
                sort_order INT DEFAULT 0,
                enabled TINYINT(1) DEFAULT 1,
                is_urgent TINYINT(1) DEFAULT 0,
                builtin TINYINT(1) DEFAULT 0,
                remark VARCHAR(255) DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_dict_key (dict_key),
                INDEX idx_project_id (project_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_templates (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(128) NOT NULL UNIQUE,
                description TEXT,
                stage_days VARCHAR(64) DEFAULT '',
                gates TEXT,
                custom_fields TEXT,
                tags TEXT,
                dict_items TEXT,
                is_default TINYINT(1) DEFAULT 0,
                created_by INT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        for col, ddl in [
            ("template_id", "ADD COLUMN template_id INT NULL"),
            ("default_sit_days", "ADD COLUMN default_sit_days INT NULL"),
            ("default_uat_days", "ADD COLUMN default_uat_days INT NULL"),
            ("default_pre_days", "ADD COLUMN default_pre_days INT NULL"),
        ]:
            if not conn.execute(text(f"SHOW COLUMNS FROM projects LIKE '{col}'")).fetchone():
                conn.execute(text(f"ALTER TABLE projects {ddl}"))
        # 历史缺陷严重程度默认值曾写为「中」,与校验集合(致命/严重/一般/提示)不一致
        conn.execute(text("ALTER TABLE defects ALTER COLUMN severity SET DEFAULT '一般'"))
        # ===================== P2-4: 操作日志防篡改哈希链 =====================
        for col, ddl in [
            ("prev_hash", "ADD COLUMN prev_hash VARCHAR(64) DEFAULT ''"),
            ("row_hash", "ADD COLUMN row_hash VARCHAR(64) DEFAULT ''"),
        ]:
            if not conn.execute(text(f"SHOW COLUMNS FROM operation_logs LIKE '{col}'")).fetchone():
                conn.execute(text(f"ALTER TABLE operation_logs {ddl}"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_chain_state (
                id INT PRIMARY KEY,
                last_log_id INT DEFAULT 0,
                head_hash VARCHAR(64) DEFAULT '',
                log_count INT DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """))
        # ===================== 补齐 ALTER 加列时遗漏的外键约束 =====================
        # 上面用 ALTER TABLE ADD COLUMN 补的列没有 FK,历史上删除父行会留下孤儿引用,
        # 也导致模型里的 ondelete=CASCADE/SET NULL 在数据库层失效。先清孤儿,再补建约束。
        fk_repairs = [
            ("testruns", "plan_id", "testplans", "CASCADE"),
            ("testruns", "round_id", "test_rounds", "SET NULL"),
            ("defects", "run_id", "testruns", "SET NULL"),
            ("testcases", "reviewer_id", "users", "SET NULL"),
            ("testcases", "folder_id", "testcase_folders", "SET NULL"),
            ("testruns", "env_id", "test_environments", "SET NULL"),
            ("projects", "template_id", "project_templates", "SET NULL"),
        ]
        for tbl, col, ref, rule in fk_repairs:
            try:
                exists = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.KEY_COLUMN_USAGE "
                        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:tbl AND COLUMN_NAME=:col "
                        "AND REFERENCED_TABLE_NAME IS NOT NULL"
                    ),
                    {"tbl": tbl, "col": col},
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    text(
                        f"UPDATE {tbl} x LEFT JOIN {ref} y ON x.{col}=y.id "
                        f"SET x.{col}=NULL WHERE x.{col} IS NOT NULL AND y.id IS NULL"
                    )
                )
                conn.execute(
                    text(
                        f"ALTER TABLE {tbl} ADD CONSTRAINT fk_{tbl}_{col} "
                        f"FOREIGN KEY ({col}) REFERENCES {ref}(id) ON DELETE {rule}"
                    )
                )
            except Exception as e:  # 约束补建失败不应阻塞启动
                print(f"[migrate] 外键 {tbl}.{col} 补建跳过: {e}")
        conn.commit()

    # 历史日志补哈希:只能保证补写之后的可验证性
    from . import audit
    from .database import SessionLocal
    with SessionLocal() as s:
        n = audit.backfill(s)
    if n:
        print(f"[migrate] 已为 {n} 条历史操作日志补写防篡改哈希链")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时:建表 + 迁移 + 初始化管理员
    Base.metadata.create_all(bind=engine)
    migrate()
    seed_admin()
    seed_dictionary()
    seed_default_template()
    # 阶段到期提醒:启动补一次,之后按周期扫描(单进程部署,重复启动由当日去重兜底)
    start_stage_scheduler()
    yield


def seed_dictionary():
    """把内置字典默认项落库(全局行),已存在则跳过;读取侧对空表也有代码兜底"""
    from .database import SessionLocal
    from .dictionaries import seed_defaults

    db = SessionLocal()
    try:
        added = seed_defaults(db)
        db.commit()
        if added:
            print(f"[migrate] 数据字典默认项写入 {added} 条")
    except Exception as e:  # 字典播种失败不应阻塞启动
        db.rollback()
        print(f"[migrate] 数据字典播种跳过: {e}")
    finally:
        db.close()


def seed_default_template():
    """内置一个「银行标准三阶段」模板:阶段天数 + 常用门禁,新项目可直接套用"""
    import json

    from sqlalchemy import select
    from .database import SessionLocal
    from .models import ProjectTemplate

    db = SessionLocal()
    try:
        existing = db.execute(select(ProjectTemplate).order_by(ProjectTemplate.id)).scalars().all()
        if existing:
            # 默认模板被删后不留空档,否则新建项目失去默认套用来源
            if not any(t.is_default for t in existing):
                existing[0].is_default = True
                db.commit()
                print(f"[migrate] 已恢复默认项目模板「{existing[0].name}」")
            return
        db.add(ProjectTemplate(
            name="银行标准三阶段模板",
            description="SIT 10天/UAT 5天/PRE 2天;准出:执行率100%、通过率>=95%、未关闭紧急缺陷=0;准入:用例评审通过>=90%",
            stage_days=json.dumps({"SIT": 10, "UAT": 5, "PRE": 2}, ensure_ascii=False),
            gates=json.dumps([
                {"stage": "SIT", "kind": "准出", "rule": "executed_rate_min", "threshold": 100, "enabled": True},
                {"stage": "SIT", "kind": "准出", "rule": "pass_rate_min", "threshold": 95, "enabled": True},
                {"stage": "SIT", "kind": "准出", "rule": "open_critical_defects_max", "threshold": 0, "enabled": True},
                {"stage": "UAT", "kind": "准入", "rule": "review_approved_min", "threshold": 90, "enabled": True},
            ], ensure_ascii=False),
            custom_fields=json.dumps([
                {"name": "测试设备", "field_type": "text", "required": False, "sort_order": 1},
                {"name": "是否自动化覆盖", "field_type": "select", "options": ["是", "否"],
                 "required": False, "sort_order": 2},
            ], ensure_ascii=False),
            tags=json.dumps([{"name": "冒烟", "color": "#E6A23C"}, {"name": "回归", "color": "#409EFF"}],
                            ensure_ascii=False),
            dict_items="", is_default=True,
        ))
        db.commit()
        print("[migrate] 已创建默认项目模板「银行标准三阶段模板」")
    except Exception as e:  # 模板播种失败不应阻塞启动
        db.rollback()
        print(f"[migrate] 默认模板播种跳过: {e}")
    finally:
        db.close()


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
app.include_router(integrations.router)
app.include_router(todo.router)
app.include_router(gates.router)
app.include_router(environments.router)
app.include_router(data_dict.router)
app.include_router(templates.router)
app.include_router(lineage.router)

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
