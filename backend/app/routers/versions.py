from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_project_access
from ..logger import log_op
from ..models import TestCase, TestCaseVersion, User
from ..schemas import TestCaseVersionOut

router = APIRouter(prefix="/api/testcases", tags=["用例版本"], dependencies=[Depends(get_current_user)])


def _save_version(db: Session, testcase: TestCase, user: User, change_summary: str = ""):
    latest = db.execute(
        select(TestCaseVersion)
        .where(TestCaseVersion.testcase_id == testcase.id)
        .order_by(TestCaseVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_version = (latest.version + 1) if latest else 1

    v = TestCaseVersion(
        testcase_id=testcase.id,
        version=next_version,
        module=testcase.module,
        title=testcase.title,
        precondition=testcase.precondition,
        steps=testcase.steps,
        expected=testcase.expected,
        priority=testcase.priority,
        changed_by=user.id,
        change_summary=change_summary,
    )
    db.add(v)
    return v


@router.get("/{testcase_id}/versions", response_model=list[TestCaseVersionOut])
def list_versions(
    testcase_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    tc = db.get(TestCase, testcase_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
    require_project_access(tc.project_id, db, current)

    versions = list(db.execute(
        select(TestCaseVersion)
        .where(TestCaseVersion.testcase_id == testcase_id)
        .order_by(TestCaseVersion.version.desc())
    ).scalars())

    result = []
    for v in versions:
        changer = db.get(User, v.changed_by)
        result.append(TestCaseVersionOut(
            id=v.id, testcase_id=v.testcase_id, version=v.version,
            module=v.module, title=v.title, precondition=v.precondition,
            steps=v.steps, expected=v.expected, priority=v.priority,
            changed_by=v.changed_by,
            changed_by_name=changer.display_name if changer else "",
            changed_at=v.changed_at, change_summary=v.change_summary,
        ))
    return result


@router.get("/{testcase_id}/versions/{version_id}")
def get_version(
    testcase_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    tc = db.get(TestCase, testcase_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
    require_project_access(tc.project_id, db, current)

    v = db.get(TestCaseVersion, version_id)
    if not v or v.testcase_id != testcase_id:
        raise HTTPException(404, "版本不存在")

    changer = db.get(User, v.changed_by)
    return TestCaseVersionOut(
        id=v.id, testcase_id=v.testcase_id, version=v.version,
        module=v.module, title=v.title, precondition=v.precondition,
        steps=v.steps, expected=v.expected, priority=v.priority,
        changed_by=v.changed_by,
        changed_by_name=changer.display_name if changer else "",
        changed_at=v.changed_at, change_summary=v.change_summary,
    )


@router.post("/{testcase_id}/versions/{version_id}/rollback")
def rollback_to_version(
    testcase_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    tc = db.get(TestCase, testcase_id)
    if not tc:
        raise HTTPException(404, "用例不存在")
    require_project_access(tc.project_id, db, current)

    v = db.get(TestCaseVersion, version_id)
    if not v or v.testcase_id != testcase_id:
        raise HTTPException(404, "版本不存在")

    _save_version(db, tc, current, f"回滚到版本{v.version}前的自动快照")

    tc.module = v.module
    tc.title = v.title
    tc.precondition = v.precondition
    tc.steps = v.steps
    tc.expected = v.expected
    tc.priority = v.priority

    log_op(db, current, "回滚", target=f"用例#{tc.id}", detail=f"回滚到版本{v.version}")
    db.commit()
    return {"detail": f"已回滚到版本 {v.version}"}
