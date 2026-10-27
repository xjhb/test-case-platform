from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_project_ids, get_current_user, require_admin, require_project_access
from ..logger import log_op
from ..models import Project, User
from ..schemas import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["项目"], dependencies=[Depends(get_current_user)])


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
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    log_op(db, current, "创建", target=f"项目#{project.id} {project.name}")
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
