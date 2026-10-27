from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..logger import log_op
from ..models import Team, User, team_members, user_projects
from ..schemas import TeamCreate, TeamMemberAdd, TeamOut, TeamUpdate

router = APIRouter(prefix="/api/teams", tags=["团队管理"], dependencies=[Depends(get_current_user)])

STAGE_ORDER = ["SIT", "UAT", "PRE"]


def _user_name(db: Session, uid: int | None) -> str:
    if not uid:
        return ""
    u = db.get(User, uid)
    return (u.display_name or u.username) if u else ""


def _team_out(db: Session, team: Team) -> dict:
    count = db.execute(
        select(team_members.c.user_id).where(team_members.c.team_id == team.id)
    ).all()
    return {
        "id": team.id,
        "name": team.name,
        "system": team.system,
        "description": team.description,
        "leader_id": team.leader_id,
        "leader_name": _user_name(db, team.leader_id),
        "created_by": team.created_by,
        "created_by_name": _user_name(db, team.created_by),
        "created_at": team.created_at,
        "updated_at": team.updated_at,
        "member_count": len(count),
    }


@router.get("", response_model=list[TeamOut])
def list_teams(db: Session = Depends(get_db)):
    teams = list(db.execute(select(Team).order_by(Team.id.desc())).scalars())
    return [_team_out(db, t) for t in teams]


@router.post("", response_model=TeamOut, dependencies=[Depends(require_admin)])
def create_team(payload: TeamCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    team = Team(
        name=payload.name,
        system=payload.system,
        description=payload.description,
        leader_id=payload.leader_id,
        created_by=current.id,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    log_op(db, current, "创建", target=f"团队#{team.id} {team.name}")
    return _team_out(db, team)


@router.put("/{team_id}", response_model=TeamOut, dependencies=[Depends(require_admin)])
def update_team(team_id: int, payload: TeamUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    if payload.name is not None:
        team.name = payload.name
    if payload.system is not None:
        team.system = payload.system
    if payload.description is not None:
        team.description = payload.description
    if payload.leader_id is not None:
        team.leader_id = payload.leader_id
    db.commit()
    db.refresh(team)
    log_op(db, current, "编辑", target=f"团队#{team.id} {team.name}")
    return _team_out(db, team)


@router.delete("/{team_id}", dependencies=[Depends(require_admin)])
def delete_team(team_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    name = team.name
    db.execute(team_members.delete().where(team_members.c.team_id == team_id))
    db.delete(team)
    db.commit()
    log_op(db, current, "删除", target=f"团队#{team_id} {name}")
    return {"ok": True}


@router.get("/{team_id}/members")
def list_members(team_id: int, db: Session = Depends(get_db)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    rows = db.execute(
        select(team_members.c.user_id, team_members.c.department)
        .where(team_members.c.team_id == team_id)
    ).all()
    members = []
    for uid, dept in rows:
        u = db.get(User, uid)
        if not u:
            continue
        pids = [r[0] for r in db.execute(
            select(user_projects.c.project_id).where(user_projects.c.user_id == uid)
        ).all()]
        members.append({
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
            "department": dept or "",
            "is_leader": team.leader_id == u.id,
            "project_ids": pids,
        })
    return members


@router.post("/{team_id}/members", dependencies=[Depends(require_admin)])
def add_member(team_id: int, payload: TeamMemberAdd, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    exists = db.execute(
        select(team_members.c.user_id)
        .where(team_members.c.team_id == team_id, team_members.c.user_id == payload.user_id)
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="该用户已在团队中")
    db.execute(team_members.insert().values(
        team_id=team_id, user_id=payload.user_id, department=payload.department
    ))
    db.commit()
    log_op(db, current, "分配", target=f"团队#{team_id} 成员#{payload.user_id}", detail=f"部门:{payload.department}")
    return {"ok": True}


@router.delete("/{team_id}/members/{uid}", dependencies=[Depends(require_admin)])
def remove_member(team_id: int, uid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    db.execute(
        team_members.delete()
        .where(team_members.c.team_id == team_id, team_members.c.user_id == uid)
    )
    db.commit()
    log_op(db, current, "删除", target=f"团队#{team_id} 成员#{uid}")
    return {"ok": True}


@router.get("/users/list", dependencies=[Depends(require_admin)])
def list_all_users_for_select(db: Session = Depends(get_db)):
    """供团队添加成员时选择的用户列表"""
    users = list(db.execute(select(User).order_by(User.id.asc())).scalars())
    return [{"id": u.id, "username": u.username, "display_name": u.display_name} for u in users]
