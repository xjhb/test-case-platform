from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="member")  # admin / member
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 外包人员信息字段
    employee_no: Mapped[str] = mapped_column(String(64), default="", index=True)  # 员工编号
    category: Mapped[str] = mapped_column(String(32), default="")  # 员工类别
    room: Mapped[str] = mapped_column(String(64), default="")  # 室
    group_name: Mapped[str] = mapped_column("group", String(64), default="")  # 组(列名group是保留字)
    join_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 入职时间
    vendor: Mapped[str] = mapped_column(String(128), default="")  # 供应商名称
    system_name: Mapped[str] = mapped_column(String(128), default="")  # 系统名称
    terminal_no: Mapped[str] = mapped_column(String(64), default="", index=True)  # 终端号
    employment_status: Mapped[str] = mapped_column(String(16), default="在职")  # 在职状态
    password_updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())  # 密码最后更新时间
    # 是否必须修改密码(管理员重置后置1,改密成功后清零)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # 新增字段
    project_no: Mapped[str] = mapped_column(String(64), default="")  # 项目编号
    level: Mapped[str] = mapped_column(String(32), default="")  # 项目等级
    project_type: Mapped[str] = mapped_column(String(64), default="")  # 项目类型
    test_manager: Mapped[str] = mapped_column(String(64), default="")  # 测试经理
    tech_manager: Mapped[str] = mapped_column(String(64), default="")  # 技术经理
    sa: Mapped[str] = mapped_column(String(64), default="")  # SA
    is_key_project: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否重点项目
    is_started: Mapped[bool] = mapped_column(Boolean, default=False)  # 启动状态
    starred: Mapped[bool] = mapped_column(Boolean, default=False)  # 关注(星标)


class TestCase(Base):
    __tablename__ = "testcases"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    module: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(String(255), index=True)
    precondition: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(8), default="P1")  # P0/P1/P2/P3
    status: Mapped[str] = mapped_column(String(16), default="未执行")  # 未执行/通过/失败/阻塞
    review_status: Mapped[str] = mapped_column(String(16), default="草稿")  # 草稿/评审中/已批准/已驳回
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_comment: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("testcase_folders.id", ondelete="SET NULL"), nullable=True, index=True)  # 所属文件夹


class TestPlan(Base):
    __tablename__ = "testplans"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(64))  # 版本/轮次,如 v1.0
    current_stage: Mapped[str] = mapped_column(String(8), default="SIT")  # SIT/UAT/PRE
    status: Mapped[str] = mapped_column(String(16), default="进行中")  # 进行中/已完成
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # 三阶段时间限制
    sit_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sit_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uat_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uat_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pre_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pre_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TestRun(Base):
    __tablename__ = "testruns"

    id: Mapped[int] = mapped_column(primary_key=True)
    testcase_id: Mapped[int] = mapped_column(ForeignKey("testcases.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("testplans.id", ondelete="CASCADE"), index=True, nullable=True)
    stage: Mapped[str] = mapped_column(String(8), default="SIT")  # SIT/UAT/PRE
    status: Mapped[str] = mapped_column(String(16))  # 通过/失败/阻塞
    remark: Mapped[str] = mapped_column(Text, default="")
    screenshot: Mapped[str] = mapped_column(String(500), default="")  # 通过时的成功截图URL
    executed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    executed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    round_id: Mapped[int | None] = mapped_column(ForeignKey("test_rounds.id", ondelete="SET NULL"), nullable=True, index=True)  # 所属轮次


# 成员-项目 多对多分配表(成员只能看到分配给自己的项目)
user_projects = Table(
    "user_projects",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
)


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")  # 冗余存用户名,避免用户删除后日志无主
    action: Mapped[str] = mapped_column(String(32), index=True)  # 登录/创建/编辑/删除/执行/推进/导入/导出/分配
    target: Mapped[str] = mapped_column(String(128), default="")  # 操作对象描述,如"用例#12"
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class SystemConfig(Base):
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_timeout_minutes: Mapped[int] = mapped_column(default=30)  # 登录超时(分钟)
    password_expire_days: Mapped[int] = mapped_column(default=30)  # 密码有效期(天)
    password_remind_days: Mapped[int] = mapped_column(default=10)  # 到期前提醒天数
    default_sit_days: Mapped[int] = mapped_column(default=7)  # SIT默认天数
    default_uat_days: Mapped[int] = mapped_column(default=5)  # UAT默认天数
    default_pre_days: Mapped[int] = mapped_column(default=3)  # PRE默认天数
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))  # 团队名称
    system: Mapped[str] = mapped_column(String(128), default="")  # 所属系统
    description: Mapped[str] = mapped_column(Text, default="")  # 团队说明
    leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # 团队负责人
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 团队-成员 多对多(成员额外有部门字段)
team_members = Table(
    "team_members",
    Base.metadata,
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("department", String(128), default=""),  # 部门
)


class Defect(Base):
    __tablename__ = "defects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="中")  # 致命/严重/一般/提示
    priority: Mapped[str] = mapped_column(String(8), default="P1")  # P0/P1/P2/P3
    status: Mapped[str] = mapped_column(String(16), default="新建")  # 新建/处理中/已修复/已验证/关闭/重新打开
    testcase_id: Mapped[int | None] = mapped_column(ForeignKey("testcases.id", ondelete="SET NULL"), nullable=True, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("testplans.id", ondelete="SET NULL"), nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("testruns.id", ondelete="SET NULL"), nullable=True, index=True)  # 关联执行记录
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))  # 提交人
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # 指派人
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TestCaseVersion(Base):
    __tablename__ = "testcase_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    testcase_id: Mapped[int] = mapped_column(ForeignKey("testcases.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(default=1)  # 版本号
    module: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(String(255))
    precondition: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(8), default="P1")
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    change_summary: Mapped[str] = mapped_column(String(255), default="")  # 修改说明


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)  # 接收人
    type: Mapped[str] = mapped_column(String(32), index=True)  # defect_assigned / testcase_assigned / stage_expiring / mention
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(255), default="")  # 前端跳转链接
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class TestReport(Base):
    __tablename__ = "test_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("testplans.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(8), default="SIT")  # SIT/UAT/PRE
    title: Mapped[str] = mapped_column(String(255))
    total_cases: Mapped[int] = mapped_column(default=0)
    passed_cases: Mapped[int] = mapped_column(default=0)
    failed_cases: Mapped[int] = mapped_column(default=0)
    blocked_cases: Mapped[int] = mapped_column(default=0)
    unexecuted_cases: Mapped[int] = mapped_column(default=0)
    pass_rate: Mapped[float] = mapped_column(default=0.0)
    defect_count: Mapped[int] = mapped_column(default=0)
    critical_defects: Mapped[int] = mapped_column(default=0)
    generated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    summary: Mapped[str] = mapped_column(Text, default="")  # 报告总结(JSON格式存储详细数据)


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    req_no: Mapped[str] = mapped_column(String(64), index=True)  # 需求编号
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(8), default="中")  # 高/中/低
    status: Mapped[str] = mapped_column(String(16), default="待处理")  # 待处理/进行中/已完成/已关闭
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 需求-用例 多对多关系
requirement_testcases = Table(
    "requirement_testcases",
    Base.metadata,
    Column("requirement_id", ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True),
    Column("testcase_id", ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True),
)


# ===================== P2: RBAC 项目角色 =====================
class ProjectRole(Base):
    """项目级角色: manager(项目经理) / test_lead(测试负责人) / tester(测试员) / viewer(只读)"""
    __tablename__ = "project_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="tester")  # manager / test_lead / tester / viewer


# ===================== P2: 用例目录树 =====================
class TestCaseFolder(Base):
    __tablename__ = "testcase_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("testcase_folders.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ===================== P2: 测试轮次 =====================
class TestRound(Base):
    """计划下的测试轮次(第1轮/第2轮/回归轮等)"""
    __tablename__ = "test_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("testplans.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))  # 如 "第1轮" / "回归轮"
    round_number: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(16), default="进行中")  # 进行中/已完成
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ===================== P2: 标签系统 =====================
class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    color: Mapped[str] = mapped_column(String(16), default="#409EFF")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# 用例-标签 多对多
testcase_tags = Table(
    "testcase_tags",
    Base.metadata,
    Column("testcase_id", ForeignKey("testcases.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


# ===================== P2: 自定义字段 =====================
class CustomField(Base):
    """项目级自定义字段定义"""
    __tablename__ = "custom_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))  # 字段名
    field_type: Mapped[str] = mapped_column(String(16), default="text")  # text / select / number / date
    options: Mapped[str] = mapped_column(Text, default="")  # select类型的选项(JSON数组)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CustomFieldValue(Base):
    """用例的自定义字段值"""
    __tablename__ = "custom_field_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("custom_fields.id", ondelete="CASCADE"), index=True)
    testcase_id: Mapped[int] = mapped_column(ForeignKey("testcases.id", ondelete="CASCADE"), index=True)
    value: Mapped[str] = mapped_column(Text, default="")
