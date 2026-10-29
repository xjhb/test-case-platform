from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- 通用 ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: str | None = None
    password_expiring: bool = False
    password_days_left: int | None = None
    password_expired: bool = False
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


# ---------- 用户 ----------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str | None = None
    employee_no: str = ""
    category: str = ""
    room: str = ""
    group: str = ""
    join_date: str | None = None
    vendor: str = ""
    system_name: str = ""
    terminal_no: str = ""
    employment_status: str = "在职"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    employee_no: str = ""
    category: str = ""
    room: str = ""
    group: str = ""
    join_date: str | None = None
    vendor: str = ""
    system_name: str = ""
    terminal_no: str = ""
    employment_status: str = "在职"
    email: str = ""
    phone: str = ""


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    employee_no: str | None = None
    category: str | None = None
    room: str | None = None
    group: str | None = None
    join_date: str | None = None
    vendor: str | None = None
    system_name: str | None = None
    terminal_no: str | None = None
    employment_status: str | None = None


class ProfileUpdate(BaseModel):
    """用户更新个人信息"""
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None


class UserWithProjects(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    project_ids: list[int] = []


class UserProjectsAssign(BaseModel):
    project_ids: list[int] = []


class LoginRequest(BaseModel):
    username: str
    password: str


# ---------- 项目 ----------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    project_no: str = ""
    level: str = ""
    project_type: str = ""
    test_manager: str = ""
    tech_manager: str = ""
    sa: str = ""
    is_key_project: bool = False
    is_started: bool = False


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = None
    project_no: str | None = None
    level: str | None = None
    project_type: str | None = None
    test_manager: str | None = None
    tech_manager: str | None = None
    sa: str | None = None
    is_key_project: bool | None = None
    is_started: bool | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    created_at: datetime
    project_no: str = ""
    level: str = ""
    project_type: str = ""
    test_manager: str = ""
    tech_manager: str = ""
    sa: str = ""
    is_key_project: bool = False
    is_started: bool = False
    starred: bool = False


# ---------- 测试用例 ----------
class TestCaseCreate(BaseModel):
    project_id: int
    module: str = ""
    title: str = Field(min_length=1, max_length=255)
    precondition: str = ""
    steps: str = ""
    expected: str = ""
    priority: str = "P1"


class TestCaseUpdate(BaseModel):
    module: str | None = None
    title: str | None = Field(default=None, max_length=255)
    precondition: str | None = None
    steps: str | None = None
    expected: str | None = None
    priority: str | None = None


class TestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    module: str
    title: str
    precondition: str
    steps: str
    expected: str
    priority: str
    status: str
    review_status: str = "草稿"
    reviewer_id: Optional[int] = None
    reviewer_name: str = ""
    review_comment: Optional[str] = ""
    reviewed_at: Optional[datetime] = None
    created_by: int
    created_at: datetime
    updated_at: datetime
    folder_id: Optional[int] = None

    @field_validator('review_comment', mode='before')
    @classmethod
    def validate_review_comment(cls, v):
        return v if v is not None else ""


# ---------- 测试计划(版本/轮次) ----------
class TestPlanCreate(BaseModel):
    project_id: int
    version: str = Field(min_length=1, max_length=64)


class StageTimeUpdate(BaseModel):
    sit_start: str | None = None
    sit_end: str | None = None
    uat_start: str | None = None
    uat_end: str | None = None
    pre_start: str | None = None
    pre_end: str | None = None


class StageAdvance(BaseModel):
    """阶段推进请求，支持跳转到任意阶段"""
    target_stage: str | None = None  # 目标阶段，不传则推进到下一阶段


class TestPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    version: str
    current_stage: str
    status: str
    created_by: int
    created_at: datetime
    sit_start: str | None = None
    sit_end: str | None = None
    uat_start: str | None = None
    uat_end: str | None = None
    pre_start: str | None = None
    pre_end: str | None = None


# ---------- 测试执行 ----------
class TestRunCreate(BaseModel):
    plan_id: int
    testcase_id: int
    status: str  # 通过/失败/阻塞
    remark: str = ""
    screenshot: str = ""  # 通过时必填,成功截图URL
    stage: str | None = None  # 执行阶段 SIT/UAT/PRE;不传则用计划当前阶段


class TestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    testcase_id: int
    plan_id: int | None = None
    round_id: int | None = None
    stage: str
    status: str
    remark: str
    screenshot: str
    executed_by: int
    executed_at: datetime


# ---------- 操作日志 ----------
class OperationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None = None
    username: str
    action: str
    target: str
    detail: str
    ip: str
    created_at: datetime


# ---------- 团队 ----------
class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    system: str = ""
    description: str = ""
    leader_id: int | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    system: str | None = None
    description: str | None = None
    leader_id: int | None = None


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    system: str
    description: str
    leader_id: int | None = None
    leader_name: str = ""
    created_by: int
    created_by_name: str = ""
    created_at: datetime
    updated_at: datetime
    member_count: int = 0


class TeamMemberAdd(BaseModel):
    user_id: int
    department: str = ""


class TeamMemberOut(BaseModel):
    id: int  # 用户编号
    username: str
    display_name: str
    role: str
    department: str
    is_leader: bool
    project_ids: list[int] = []


# ---------- 缺陷 ----------
class DefectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    severity: str = "中"  # 致命/严重/一般/提示
    priority: str = "P1"
    testcase_id: int | None = None
    plan_id: int | None = None
    run_id: int | None = None
    project_id: int
    assignee_id: int | None = None


class DefectUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    severity: str | None = None
    priority: str | None = None
    status: str | None = None
    assignee_id: int | None = None


class DefectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    severity: str
    priority: str
    status: str
    testcase_id: int | None = None
    plan_id: int | None = None
    run_id: int | None = None
    project_id: int
    reporter_id: int
    reporter_name: str = ""
    assignee_id: int | None = None
    assignee_name: str = ""
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None


# ---------- 用例版本 ----------
class TestCaseVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    testcase_id: int
    version: int
    module: str
    title: str
    precondition: str
    steps: str
    expected: str
    priority: str
    changed_by: int
    changed_by_name: str = ""
    changed_at: datetime
    change_summary: str


# ---------- 通知 ----------
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    type: str
    title: str
    content: str
    link: str
    is_read: bool
    created_at: datetime


class NotificationMarkRead(BaseModel):
    ids: list[int] = []


# ---------- 测试报告 ----------
class TestReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plan_id: int
    stage: str
    title: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    blocked_cases: int
    unexecuted_cases: int
    pass_rate: float
    defect_count: int
    critical_defects: int
    generated_by: int
    generated_by_name: str = ""
    generated_at: datetime
    summary: str


# ---------- 需求 ----------
class RequirementCreate(BaseModel):
    project_id: int
    req_no: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    priority: str = "中"
    status: str = "待处理"


class RequirementUpdate(BaseModel):
    req_no: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    priority: str | None = None
    status: str | None = None


class RequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    req_no: str
    title: str
    description: str
    priority: str
    status: str
    created_by: int
    created_by_name: str = ""
    created_at: datetime
    updated_at: datetime
    testcase_count: int = 0


class CoverageMatrixItem(BaseModel):
    requirement_id: int
    req_no: str
    req_title: str
    req_priority: str
    req_status: str
    testcase_ids: list[int]
    testcase_count: int
    covered: bool


# ===================== P2: RBAC 项目角色 =====================
class ProjectRoleAssign(BaseModel):
    user_id: int
    role: str = "tester"  # 角色代码，必须是系统中存在的角色


class ProjectRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    username: str = ""
    display_name: str = ""


# ===================== P2: 系统角色定义 =====================
class RoleDefinitionCreate(BaseModel):
    role_code: str = Field(min_length=1, max_length=32)
    role_name: str = Field(min_length=1, max_length=64)
    description: str = ""
    sort_order: int = 0


class RoleDefinitionUpdate(BaseModel):
    role_name: str | None = None
    description: str | None = None
    sort_order: int | None = None


class RoleDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role_code: str
    role_name: str
    description: str
    is_system: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


# ===================== P2: 用例目录树 =====================
class FolderCreate(BaseModel):
    project_id: int
    parent_id: int | None = None
    name: str = Field(min_length=1, max_length=128)


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    parent_id: int | None = None
    sort_order: int | None = None


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    parent_id: int | None = None
    name: str
    sort_order: int = 0
    children: list["FolderOut"] = []
    testcase_count: int = 0


# ===================== P2: 测试轮次 =====================
class TestRoundCreate(BaseModel):
    plan_id: int
    name: str = Field(min_length=1, max_length=64)


class TestRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plan_id: int
    name: str
    round_number: int
    status: str
    created_by: int
    created_at: datetime
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0


# ===================== P2: 批量执行 =====================
class BatchExecuteItem(BaseModel):
    testcase_id: int
    status: str  # 通过/失败/阻塞/跳过
    remark: str = ""
    screenshot: str = ""


class BatchExecuteRequest(BaseModel):
    plan_id: int
    round_id: int | None = None
    stage: str | None = None
    items: list[BatchExecuteItem]


class BatchExecuteResult(BaseModel):
    total: int
    success: int
    failed: int


# ===================== P2: 标签 =====================
class TagCreate(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=64)
    color: str = "#409EFF"


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    color: str


class TagAssign(BaseModel):
    tag_ids: list[int]


# ===================== P2: 自定义字段 =====================
class CustomFieldCreate(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=64)
    field_type: str = "text"  # text / select / number / date
    options: str = ""  # JSON array for select type
    required: bool = False


class CustomFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    field_type: str
    options: str
    required: bool
    sort_order: int = 0


class CustomFieldValueSet(BaseModel):
    field_id: int
    value: str


class CustomFieldValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_id: int
    field_name: str = ""
    field_type: str = ""
    testcase_id: int
    value: str
