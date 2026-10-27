from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_project_ids, get_current_user, require_project_access
from ..logger import log_op
from ..models import Requirement, TestCase, User, requirement_testcases
from ..schemas import CoverageMatrixItem, RequirementCreate, RequirementOut, RequirementUpdate

router = APIRouter(prefix="/api/requirements", tags=["需求管理"], dependencies=[Depends(get_current_user)])


@router.get("/coverage/matrix")
def coverage_matrix(
    project_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取需求覆盖率矩阵"""
    require_project_access(project_id, db, current)

    requirements = list(
        db.execute(select(Requirement).where(Requirement.project_id == project_id).order_by(Requirement.id.asc())).scalars()
    )

    matrix = []
    for req in requirements:
        tc_ids = [
            row.testcase_id
            for row in db.execute(
                select(requirement_testcases.c.testcase_id).where(requirement_testcases.c.requirement_id == req.id)
            ).all()
        ]
        matrix.append(
            CoverageMatrixItem(
                requirement_id=req.id,
                req_no=req.req_no,
                req_title=req.title,
                req_priority=req.priority,
                req_status=req.status,
                testcase_ids=tc_ids,
                testcase_count=len(tc_ids),
                covered=len(tc_ids) > 0,
            )
        )

    total_reqs = len(matrix)
    covered_reqs = sum(1 for item in matrix if item.covered)
    coverage_rate = (covered_reqs / total_reqs * 100) if total_reqs > 0 else 0

    return {
        "project_id": project_id,
        "total_requirements": total_reqs,
        "covered_requirements": covered_reqs,
        "uncovered_requirements": total_reqs - covered_reqs,
        "coverage_rate": round(coverage_rate, 2),
        "matrix": matrix,
    }


@router.get("")
def list_requirements(
    project_id: int | None = None,
    priority: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    accessible = accessible_project_ids(db, current)
    q = select(Requirement)
    if project_id is not None:
        require_project_access(project_id, db, current)
        q = q.where(Requirement.project_id == project_id)
    elif accessible is not None:
        if not accessible:
            return {"total": 0, "page": page, "page_size": page_size, "items": []}
        q = q.where(Requirement.project_id.in_(accessible))
    if priority:
        q = q.where(Requirement.priority == priority)
    if status:
        q = q.where(Requirement.status == status)
    if keyword:
        kw = f"%{keyword}%"
        q = q.where(Requirement.title.like(kw) | Requirement.req_no.like(kw))

    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    items = list(db.execute(q.order_by(Requirement.id.desc()).offset((page - 1) * page_size).limit(page_size)).scalars())

    result_items = []
    for req in items:
        out = RequirementOut.model_validate(req)
        creator = db.get(User, req.created_by)
        out.created_by_name = creator.display_name or creator.username if creator else ""
        tc_count = db.execute(
            select(func.count()).select_from(requirement_testcases).where(requirement_testcases.c.requirement_id == req.id)
        ).scalar()
        out.testcase_count = tc_count or 0
        result_items.append(out)

    return {"total": total, "page": page, "page_size": page_size, "items": result_items}


@router.post("", response_model=RequirementOut)
def create_requirement(
    payload: RequirementCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_project_access(payload.project_id, db, current)
    req = Requirement(
        project_id=payload.project_id,
        req_no=payload.req_no,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        status=payload.status,
        created_by=current.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    log_op(db, current, "创建", target=f"需求#{req.id} {req.req_no}", detail=f"项目#{payload.project_id}")
    out = RequirementOut.model_validate(req)
    creator = db.get(User, req.created_by)
    out.created_by_name = creator.display_name or creator.username if creator else ""
    return out


@router.get("/{reqid}", response_model=RequirementOut)
def get_requirement(reqid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(Requirement, reqid)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    require_project_access(req.project_id, db, current)
    out = RequirementOut.model_validate(req)
    creator = db.get(User, req.created_by)
    out.created_by_name = creator.display_name or creator.username if creator else ""
    tc_count = db.execute(
        select(func.count()).select_from(requirement_testcases).where(requirement_testcases.c.requirement_id == req.id)
    ).scalar()
    out.testcase_count = tc_count or 0
    return out


@router.put("/{reqid}", response_model=RequirementOut)
def update_requirement(
    reqid: int,
    payload: RequirementUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    req = db.get(Requirement, reqid)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    require_project_access(req.project_id, db, current)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(req, k, v)
    db.commit()
    db.refresh(req)
    log_op(db, current, "编辑", target=f"需求#{req.id} {req.req_no}")
    out = RequirementOut.model_validate(req)
    creator = db.get(User, req.created_by)
    out.created_by_name = creator.display_name or creator.username if creator else ""
    tc_count = db.execute(
        select(func.count()).select_from(requirement_testcases).where(requirement_testcases.c.requirement_id == req.id)
    ).scalar()
    out.testcase_count = tc_count or 0
    return out


@router.delete("/{reqid}")
def delete_requirement(reqid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    req = db.get(Requirement, reqid)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    require_project_access(req.project_id, db, current)
    req_no = req.req_no
    db.delete(req)
    db.commit()
    log_op(db, current, "删除", target=f"需求#{reqid} {req_no}")
    return {"ok": True}


@router.post("/{reqid}/testcases")
def link_testcases(
    reqid: int,
    testcase_ids: list[int],
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """关联测试用例到需求"""
    req = db.get(Requirement, reqid)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    require_project_access(req.project_id, db, current)

    for tc_id in testcase_ids:
        tc = db.get(TestCase, tc_id)
        if not tc:
            continue
        if tc.project_id != req.project_id:
            raise HTTPException(status_code=400, detail=f"用例#{tc_id}不属于该项目")
        existing = db.execute(
            select(requirement_testcases).where(
                requirement_testcases.c.requirement_id == reqid,
                requirement_testcases.c.testcase_id == tc_id,
            )
        ).first()
        if not existing:
            db.execute(requirement_testcases.insert().values(requirement_id=reqid, testcase_id=tc_id))

    db.commit()
    log_op(db, current, "关联", target=f"需求#{reqid}", detail=f"关联{len(testcase_ids)}个用例")
    return {"ok": True, "linked": len(testcase_ids)}


@router.delete("/{reqid}/testcases/{tcid}")
def unlink_testcase(
    reqid: int,
    tcid: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """取消关联测试用例"""
    req = db.get(Requirement, reqid)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    require_project_access(req.project_id, db, current)
    db.execute(
        requirement_testcases.delete().where(
            requirement_testcases.c.requirement_id == reqid,
            requirement_testcases.c.testcase_id == tcid,
        )
    )
    db.commit()
    return {"ok": True}


@router.get("/{reqid}/testcases")
def get_linked_testcases(
    reqid: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取需求关联的测试用例"""
    req = db.get(Requirement, reqid)
    if not req:
        raise HTTPException(status_code=404, detail="需求不存在")
    require_project_access(req.project_id, db, current)

    tc_ids = [
        row.testcase_id
        for row in db.execute(
            select(requirement_testcases.c.testcase_id).where(requirement_testcases.c.requirement_id == reqid)
        ).all()
    ]
    testcases = [db.get(TestCase, tc_id) for tc_id in tc_ids]
    testcases = [tc for tc in testcases if tc]
    return testcases
