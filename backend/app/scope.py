"""计划用例范围:一旦圈选即以快照为准,未圈选的历史计划回退到项目全部用例"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PlanTestCase, TestCase, TestPlan


def has_scope(db: Session, plan: TestPlan) -> bool:
    """该计划是否已显式圈选用例"""
    return (
        db.execute(select(PlanTestCase.plan_id).where(PlanTestCase.plan_id == plan.id).limit(1)).scalar_one_or_none()
        is not None
    )


def plan_case_ids(db: Session, plan: TestPlan) -> list[int]:
    snapshot = list(
        db.execute(
            select(PlanTestCase.testcase_id)
            .where(PlanTestCase.plan_id == plan.id)
            .order_by(PlanTestCase.testcase_id)
        ).scalars()
    )
    if snapshot:
        alive = set(db.execute(select(TestCase.id).where(TestCase.id.in_(snapshot))).scalars())
        return [i for i in snapshot if i in alive]
    return list(
        db.execute(
            select(TestCase.id).where(TestCase.project_id == plan.project_id).order_by(TestCase.id)
        ).scalars()
    )


def plan_cases(db: Session, plan: TestPlan) -> list[TestCase]:
    ids = plan_case_ids(db, plan)
    if not ids:
        return []
    return list(
        db.execute(select(TestCase).where(TestCase.id.in_(ids)).order_by(TestCase.id)).scalars()
    )


def in_scope(db: Session, plan: TestPlan, testcase_id: int) -> bool:
    """用例是否属于该计划范围;未圈选时按项目归属判断"""
    if not has_scope(db, plan):
        tc = db.get(TestCase, testcase_id)
        return tc is not None and tc.project_id == plan.project_id
    return (
        db.execute(
            select(PlanTestCase.testcase_id).where(
                PlanTestCase.plan_id == plan.id, PlanTestCase.testcase_id == testcase_id
            ).limit(1)
        ).scalar_one_or_none()
        is not None
    )
