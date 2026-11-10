from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_project_ids, get_current_user, require_admin, require_project_access
from ..logger import log_op
from ..models import Project, ProjectTemplate, User
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate
from .templates import apply_template

router = APIRouter(prefix="/api/projects", tags=["项目"], dependencies=[Depends(get_current_user)])


def _resolve_template(db: Session, template_id: int | None) -> ProjectTemplate | None:
    """显式指定则必须存在;传 0 表示明确不套用;未指定时取标记为默认的模板"""
    if template_id == 0:
        return None
    if template_id is not None:
        tpl = db.get(ProjectTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=400, detail="项目模板不存在")
        return tpl
    return db.execute(select(ProjectTemplate).where(ProjectTemplate.is_default == True)).scalars().first()  # noqa: E712


STAGE_DAY_FIELDS = {
    "default_sit_days": "SIT 天数",
    "default_uat_days": "UAT 天数",
    "default_pre_days": "预发版天数",
}


def _validate_stage_days(data: dict):
    for key, label in STAGE_DAY_FIELDS.items():
        value = data.get(key)
        if value is None:
            continue
        try:
            num = int(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{label}需为 1-365 的整数")
        if not 1 <= num <= 365:
            raise HTTPException(status_code=400, detail=f"{label}需为 1-365 的整数,留空表示跟随全局阶段配置")


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ids = accessible_project_ids(db, current)
    q = select(Project)
    if ids is not None:
        if not ids:
            return []
        q = q.where(Project.id.in_(ids))
    return list(db.execute(q.order_by(Project.id.desc())).scalars())


@router.post("", response_model=ProjectOut, dependencies=[Depends(require_admin)])
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    template = _resolve_template(db, payload.template_id)
    data = payload.model_dump()
    _validate_stage_days(data)
    project = Project(
        name=payload.name,
        description=payload.description or "",
        project_no=payload.project_no,
        level=payload.level,
        project_type=payload.project_type,
        test_manager=payload.test_manager,
        tech_manager=payload.tech_manager,
        sa=payload.sa,
        is_key_project=payload.is_key_project,
        is_started=payload.is_started,
        template_id=template.id if template else None,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    stats = apply_template(db, template, project.id) if template else None
    # 创建时手填的阶段天数优先于模板带出的天数
    for key in ("default_sit_days", "default_uat_days", "default_pre_days"):
        if data.get(key) is not None:
            setattr(project, key, int(data[key]))
    db.commit()
    db.refresh(project)
    detail = f"套用模板「{template.name}」: 门禁+{stats['gates']} 字段+{stats['custom_fields']} 标签+{stats['tags']} 字典+{stats['dict_items']}" if template and stats else "未套用模板"
    log_op(db, current, "创建", target=f"项目#{project.id} {project.name}", detail=detail)
    return project


@router.get("/{pid}", response_model=ProjectOut)
def get_project(pid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(pid, db, current)
    return p


@router.put("/{pid}", response_model=ProjectOut, dependencies=[Depends(require_admin)])
def update_project(pid: int, payload: ProjectUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    data = payload.model_dump(exclude_unset=True)
    _validate_stage_days(data)
    if "template_id" in data:
        # 0 与 null 同义:只解除来源记录,不动已套用到的项目配置
        if data["template_id"] == 0:
            data["template_id"] = None
        elif data["template_id"] is not None and not db.get(ProjectTemplate, data["template_id"]):
            raise HTTPException(status_code=400, detail="项目模板不存在")
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    log_op(db, current, "编辑", target=f"项目#{p.id} {p.name}")
    return p


@router.patch("/{pid}/star")
def toggle_star(pid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """切换关注星标"""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    require_project_access(pid, db, current)
    p.starred = not p.starred
    db.commit()
    db.refresh(p)
    return {"starred": p.starred}


@router.delete("/{pid}", dependencies=[Depends(require_admin)])
def delete_project(pid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    name = p.name
    db.delete(p)
    db.commit()
    log_op(db, current, "删除", target=f"项目#{pid} {name}")
    return {"ok": True}
