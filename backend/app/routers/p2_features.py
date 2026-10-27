"""P2 功能路由: RBAC角色、用例目录树、标签、自定义字段、测试轮次、批量执行"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin, require_can_edit, require_can_manage, require_project_access
from ..logger import log_op
from ..models import (
    CustomField, CustomFieldValue, ProjectRole, Tag, TestCase, TestCaseFolder,
    TestPlan, TestRound, TestRun, User, testcase_tags, user_projects,
)
from ..schemas import (
    BatchExecuteItem, BatchExecuteRequest, BatchExecuteResult,
    CustomFieldCreate, CustomFieldOut, CustomFieldValueOut, CustomFieldValueSet,
    FolderCreate, FolderOut, FolderUpdate,
    ProjectRoleAssign, ProjectRoleOut,
    TagAssign, TagCreate, TagOut,
    TestRoundCreate, TestRoundOut,
)

router = APIRouter(prefix="/api/p2", tags=["P2功能"], dependencies=[Depends(get_current_user)])


# ===================== RBAC 项目角色 =====================
@router.get("/roles/{pid}")
def list_project_roles(
    pid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_project_access(pid, db, current)
    rows = db.execute(
        select(ProjectRole, User.username, User.display_name)
        .join(User, ProjectRole.user_id == User.id)
        .where(ProjectRole.project_id == pid)
    ).all()
    return [
        {"id": r.ProjectRole.id, "user_id": r.ProjectRole.user_id, "project_id": r.ProjectRole.project_id,
         "role": r.ProjectRole.role, "username": r.username, "display_name": r.display_name}
        for r in rows
    ]


@router.post("/roles/{pid}")
def assign_project_role(
    pid: int, payload: ProjectRoleAssign, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_can_manage(pid, db, current)
    if payload.role not in ("manager", "test_lead", "tester", "viewer"):
        raise HTTPException(status_code=400, detail="角色只能是 manager/test_lead/tester/viewer")
    existing = db.execute(
        select(ProjectRole).where(ProjectRole.user_id == payload.user_id, ProjectRole.project_id == pid)
    ).scalar_one_or_none()
    if existing:
        existing.role = payload.role
    else:
        db.add(ProjectRole(user_id=payload.user_id, project_id=pid, role=payload.role))
        # 同时加入 user_projects 关联
        db.execute(user_projects.insert().values(user_id=payload.user_id, project_id=pid))
    db.commit()
    log_op(db, current, "分配", target=f"项目#{pid}角色", detail=f"用户#{payload.user_id} -> {payload.role}")
    return {"ok": True}


@router.delete("/roles/{pid}/{user_id}")
def remove_project_role(
    pid: int, user_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_can_manage(pid, db, current)
    role = db.execute(
        select(ProjectRole).where(ProjectRole.user_id == user_id, ProjectRole.project_id == pid)
    ).scalar_one_or_none()
    if role:
        db.delete(role)
        db.commit()
        log_op(db, current, "删除", target=f"项目#{pid}角色", detail=f"用户#{user_id}")
    return {"ok": True}


# ===================== 用例目录树 =====================
@router.get("/folders/{pid}")
def list_folders(
    pid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_project_access(pid, db, current)
    folders = list(db.execute(
        select(TestCaseFolder).where(TestCaseFolder.project_id == pid).order_by(TestCaseFolder.sort_order)
    ).scalars())
    # 统计每个文件夹下的用例数
    counts = dict(db.execute(
        select(TestCase.folder_id, func.count(TestCase.id))
        .where(TestCase.project_id == pid, TestCase.folder_id.isnot(None))
        .group_by(TestCase.folder_id)
    ).all())
    # 构建树
    folder_map = {}
    for f in folders:
        folder_map[f.id] = FolderOut(
            id=f.id, project_id=f.project_id, parent_id=f.parent_id,
            name=f.name, sort_order=f.sort_order, testcase_count=counts.get(f.id, 0)
        )
    tree = []
    for f in folders:
        node = folder_map[f.id]
        if f.parent_id and f.parent_id in folder_map:
            folder_map[f.parent_id].children.append(node)
        else:
            tree.append(node)
    return tree


@router.post("/folders")
def create_folder(
    payload: FolderCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_can_edit(payload.project_id, db, current)
    folder = TestCaseFolder(
        project_id=payload.project_id, parent_id=payload.parent_id, name=payload.name
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    log_op(db, current, "创建", target=f"文件夹#{folder.id}", detail=payload.name)
    return {"id": folder.id, "project_id": folder.project_id, "parent_id": folder.parent_id,
            "name": folder.name, "sort_order": folder.sort_order, "children": [], "testcase_count": 0}


@router.put("/folders/{fid}")
def update_folder(
    fid: int, payload: FolderUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    folder = db.get(TestCaseFolder, fid)
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    require_can_edit(folder.project_id, db, current)
    if payload.name is not None:
        folder.name = payload.name
    if payload.parent_id is not None:
        folder.parent_id = payload.parent_id
    if payload.sort_order is not None:
        folder.sort_order = payload.sort_order
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "project_id": folder.project_id, "parent_id": folder.parent_id,
            "name": folder.name, "sort_order": folder.sort_order, "children": [], "testcase_count": 0}


@router.delete("/folders/{fid}")
def delete_folder(
    fid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    folder = db.get(TestCaseFolder, fid)
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    require_can_edit(folder.project_id, db, current)
    # 将文件夹下的用例移到根目录
    db.execute(
        TestCase.update().where(TestCase.folder_id == fid).values(folder_id=None)
    )
    db.delete(folder)
    db.commit()
    log_op(db, current, "删除", target=f"文件夹#{fid}", detail=folder.name)
    return {"ok": True}


@router.post("/testcases/{tcid}/move")
def move_testcase_to_folder(
    tcid: int, folder_id: int | None = None,
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_can_edit(tc.project_id, db, current)
    tc.folder_id = folder_id
    db.commit()
    return {"ok": True}


# ===================== 标签 =====================
@router.get("/tags/{pid}")
def list_tags(
    pid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_project_access(pid, db, current)
    return list(db.execute(select(Tag).where(Tag.project_id == pid)).scalars())


@router.post("/tags", response_model=TagOut)
def create_tag(
    payload: TagCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_can_edit(payload.project_id, db, current)
    tag = Tag(project_id=payload.project_id, name=payload.name, color=payload.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}")
def delete_tag(
    tag_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    require_can_edit(tag.project_id, db, current)
    db.delete(tag)
    db.commit()
    return {"ok": True}


@router.post("/testcases/{tcid}/tags")
def assign_tags(
    tcid: int, payload: TagAssign, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_can_edit(tc.project_id, db, current)
    # 清除旧标签, 赋新值
    db.execute(testcase_tags.delete().where(testcase_tags.c.testcase_id == tcid))
    for tid in payload.tag_ids:
        db.execute(testcase_tags.insert().values(testcase_id=tcid, tag_id=tid))
    db.commit()
    return {"ok": True}


@router.get("/testcases/{tcid}/tags")
def get_testcase_tags(
    tcid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    rows = db.execute(
        select(Tag).join(testcase_tags, Tag.id == testcase_tags.c.tag_id)
        .where(testcase_tags.c.testcase_id == tcid)
    ).scalars().all()
    return rows


# ===================== 自定义字段 =====================
@router.get("/custom-fields/{pid}")
def list_custom_fields(
    pid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_project_access(pid, db, current)
    return list(db.execute(
        select(CustomField).where(CustomField.project_id == pid).order_by(CustomField.sort_order)
    ).scalars())


@router.post("/custom-fields", response_model=CustomFieldOut)
def create_custom_field(
    payload: CustomFieldCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    require_can_manage(payload.project_id, db, current)
    field = CustomField(
        project_id=payload.project_id, name=payload.name,
        field_type=payload.field_type, options=payload.options, required=payload.required,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


@router.delete("/custom-fields/{field_id}")
def delete_custom_field(
    field_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    field = db.get(CustomField, field_id)
    if not field:
        raise HTTPException(status_code=404, detail="字段不存在")
    require_can_manage(field.project_id, db, current)
    db.execute(CustomFieldValue.delete().where(CustomFieldValue.field_id == field_id))
    db.delete(field)
    db.commit()
    return {"ok": True}


@router.get("/testcases/{tcid}/custom-fields")
def get_testcase_custom_fields(
    tcid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_project_access(tc.project_id, db, current)
    rows = db.execute(
        select(CustomFieldValue, CustomField.name, CustomField.field_type)
        .join(CustomField, CustomFieldValue.field_id == CustomField.id)
        .where(CustomFieldValue.testcase_id == tcid)
    ).all()
    return [
        {"id": r.CustomFieldValue.id, "field_id": r.CustomFieldValue.field_id,
         "field_name": r.name, "field_type": r.field_type,
         "testcase_id": r.CustomFieldValue.testcase_id, "value": r.CustomFieldValue.value}
        for r in rows
    ]


@router.post("/testcases/{tcid}/custom-fields")
def set_testcase_custom_fields(
    tcid: int, values: list[CustomFieldValueSet],
    db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    tc = db.get(TestCase, tcid)
    if not tc:
        raise HTTPException(status_code=404, detail="用例不存在")
    require_can_edit(tc.project_id, db, current)
    for v in values:
        existing = db.execute(
            select(CustomFieldValue).where(
                CustomFieldValue.testcase_id == tcid, CustomFieldValue.field_id == v.field_id
            )
        ).scalar_one_or_none()
        if existing:
            existing.value = v.value
        else:
            db.add(CustomFieldValue(field_id=v.field_id, testcase_id=tcid, value=v.value))
    db.commit()
    return {"ok": True}


# ===================== 测试轮次 =====================
@router.get("/rounds/{plan_id}")
def list_rounds(
    plan_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    plan = db.get(TestPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_project_access(plan.project_id, db, current)
    rounds = list(db.execute(
        select(TestRound).where(TestRound.plan_id == plan_id).order_by(TestRound.round_number)
    ).scalars())
    result = []
    for rd in rounds:
        total = db.execute(
            select(func.count(TestRun.id)).where(TestRun.round_id == rd.id)
        ).scalar() or 0
        passed = db.execute(
            select(func.count(TestRun.id)).where(TestRun.round_id == rd.id, TestRun.status == "通过")
        ).scalar() or 0
        failed = db.execute(
            select(func.count(TestRun.id)).where(TestRun.round_id == rd.id, TestRun.status == "失败")
        ).scalar() or 0
        result.append(TestRoundOut(
            id=rd.id, plan_id=rd.plan_id, name=rd.name, round_number=rd.round_number,
            status=rd.status, created_by=rd.created_by, created_at=rd.created_at,
            total_cases=total, passed_cases=passed, failed_cases=failed,
        ))
    return result


@router.post("/rounds")
def create_round(
    payload: TestRoundCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    plan = db.get(TestPlan, payload.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_can_manage(plan.project_id, db, current)
    max_num = db.execute(
        select(func.max(TestRound.round_number)).where(TestRound.plan_id == payload.plan_id)
    ).scalar() or 0
    rd = TestRound(plan_id=payload.plan_id, name=payload.name, round_number=max_num + 1, created_by=current.id)
    db.add(rd)
    db.commit()
    db.refresh(rd)
    log_op(db, current, "创建", target=f"轮次#{rd.id}", detail=payload.name)
    return {"id": rd.id, "plan_id": rd.plan_id, "name": rd.name, "round_number": rd.round_number,
            "status": rd.status, "created_by": rd.created_by, "created_at": rd.created_at,
            "total_cases": 0, "passed_cases": 0, "failed_cases": 0}


@router.put("/rounds/{rid}/complete")
def complete_round(
    rid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    rd = db.get(TestRound, rid)
    if not rd:
        raise HTTPException(status_code=404, detail="轮次不存在")
    plan = db.get(TestPlan, rd.plan_id)
    require_can_manage(plan.project_id, db, current)
    rd.status = "已完成"
    db.commit()
    return {"ok": True}


# ===================== 批量执行 =====================
@router.post("/batch-execute")
def batch_execute(
    payload: BatchExecuteRequest, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    plan = db.get(TestPlan, payload.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="计划不存在")
    require_can_edit(plan.project_id, db, current)
    stage = payload.stage or plan.current_stage
    success_count = 0
    fail_count = 0
    for item in payload.items:
        if item.status == "跳过":
            continue
        try:
            run = TestRun(
                testcase_id=item.testcase_id, plan_id=payload.plan_id,
                round_id=payload.round_id, stage=stage, status=item.status,
                remark=item.remark, screenshot=item.screenshot, executed_by=current.id,
            )
            db.add(run)
            # 更新用例状态
            tc = db.get(TestCase, item.testcase_id)
            if tc:
                tc.status = item.status
            success_count += 1
        except Exception:
            fail_count += 1
    db.commit()
    log_op(db, current, "执行", target=f"计划#{payload.plan_id}", detail=f"批量执行{success_count}条用例")
    return BatchExecuteResult(total=len(payload.items), success=success_count, failed=fail_count)
