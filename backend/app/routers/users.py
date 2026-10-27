import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime

from ..database import get_db
from ..deps import accessible_project_ids, get_current_user, require_admin
from ..logger import log_op
from ..models import Project, User, user_projects
from ..schemas import UserCreate, UserOut, UserProjectsAssign, UserUpdate, UserWithProjects
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["成员管理"])


def _user_project_ids(db: Session, user_id: int) -> list[int]:
    rows = db.execute(select(user_projects.c.project_id).where(user_projects.c.user_id == user_id)).all()
    return [r[0] for r in rows]


def _with_projects(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "project_ids": _user_project_ids(db, user.id),
    }


def _staff_out(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "employee_no": user.employee_no or "",
        "category": user.category or "",
        "room": user.room or "",
        "group": user.group_name or "",
        "join_date": user.join_date.strftime("%Y-%m-%d") if user.join_date else "",
        "vendor": user.vendor or "",
        "system_name": user.system_name or "",
        "terminal_no": user.terminal_no or "",
        "employment_status": user.employment_status or "在职",
    }


@router.get("/staff", dependencies=[Depends(require_admin)])
def list_staff(
    terminal_no: str | None = None,
    employee_name: str | None = None,
    join_date: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """外包人员列表(带筛选)"""
    q = select(User)
    if terminal_no:
        q = q.where(User.terminal_no.like(f"%{terminal_no}%"))
    if employee_name:
        q = q.where(User.display_name.like(f"%{employee_name}%"))
    if join_date:
        q = q.where(User.join_date.like(f"%{join_date}%"))

    all_rows = list(db.execute(q.order_by(User.id.asc())).scalars())
    total = len(all_rows)
    items = all_rows[(page - 1) * page_size : page * page_size]
    return {"total": total, "page": page, "page_size": page_size, "items": [_staff_out(u) for u in items]}


@router.get("", response_model=list[UserWithProjects], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)):
    users = list(db.execute(select(User).order_by(User.id.asc())).scalars())
    return [_with_projects(db, u) for u in users]


@router.post("", dependencies=[Depends(require_admin)])
def create_user(payload: UserCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    exists = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    join_dt = None
    if payload.join_date:
        try:
            join_dt = datetime.strptime(payload.join_date, "%Y-%m-%d")
        except ValueError:
            pass
    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        role="member",
        employee_no=payload.employee_no,
        category=payload.category,
        room=payload.room,
        group_name=payload.group,
        join_date=join_dt,
        vendor=payload.vendor,
        system_name=payload.system_name,
        terminal_no=payload.terminal_no,
        employment_status=payload.employment_status or "在职",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_op(db, current, "创建", target=f"成员#{user.id} {user.username}")
    return _staff_out(user)


@router.put("/{uid}", dependencies=[Depends(require_admin)])
def update_user(uid: int, payload: UserUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.role is not None:
        if user.id == current.id and payload.role != "admin":
            raise HTTPException(status_code=400, detail="不能取消自己的管理员角色")
        user.role = payload.role
    if payload.is_active is not None:
        if user.id == current.id and not payload.is_active:
            raise HTTPException(status_code=400, detail="不能禁用自己的账号")
        user.is_active = payload.is_active
    if payload.employee_no is not None:
        user.employee_no = payload.employee_no
    if payload.category is not None:
        user.category = payload.category
    if payload.room is not None:
        user.room = payload.room
    if payload.group is not None:
        user.group_name = payload.group
    if payload.join_date is not None:
        try:
            user.join_date = datetime.strptime(payload.join_date, "%Y-%m-%d") if payload.join_date else None
        except ValueError:
            pass
    if payload.vendor is not None:
        user.vendor = payload.vendor
    if payload.system_name is not None:
        user.system_name = payload.system_name
    if payload.terminal_no is not None:
        user.terminal_no = payload.terminal_no
    if payload.employment_status is not None:
        user.employment_status = payload.employment_status
    db.commit()
    db.refresh(user)
    log_op(db, current, "编辑", target=f"成员#{user.id} {user.username}",
           detail=f"角色:{user.role} 启用:{user.is_active}")
    return _staff_out(user)


@router.put("/{uid}/projects", dependencies=[Depends(require_admin)])
def assign_projects(uid: int, payload: UserProjectsAssign, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    valid_ids = set()
    if payload.project_ids:
        rows = db.execute(select(Project.id).where(Project.id.in_(payload.project_ids))).all()
        valid_ids = {r[0] for r in rows}
    db.execute(user_projects.delete().where(user_projects.c.user_id == uid))
    for pid in valid_ids:
        db.execute(user_projects.insert().values(user_id=uid, project_id=pid))
    db.commit()
    log_op(db, current, "分配", target=f"成员#{user.id} {user.username}",
           detail=f"项目ID: {sorted(valid_ids)}")
    return {"ok": True, "project_ids": list(valid_ids)}


@router.delete("/{uid}", dependencies=[Depends(require_admin)])
def delete_user(uid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if uid == current.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账号")
    uname = user.username
    db.execute(user_projects.delete().where(user_projects.c.user_id == uid))
    db.delete(user)
    db.commit()
    log_op(db, current, "删除", target=f"成员#{uid} {uname}")
    return {"ok": True}


def _gen_temp_password(length: int = 12) -> str:
    """生成随机临时密码:保证同时含大写/小写/数字,满足前端与后端的长度校验"""
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # 去掉 I O
    lower = "abcdefghijkmnpqrstuvwxyz"   # 去掉 l o
    digits = "23456789"                  # 去掉 0 1
    pool = upper + lower + digits
    rng = secrets.SystemRandom()
    while True:
        pwd = "".join(rng.choice(pool) for _ in range(length))
        if any(c in upper for c in pwd) and any(c in lower for c in pwd) and any(c in digits for c in pwd):
            return pwd


@router.post("/{uid}/reset-password", dependencies=[Depends(require_admin)])
def reset_password(uid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """超管重置成员密码:生成随机临时密码,仅本次返回一次,不落库明文。

    通过把 password_updated_at 置为极早时间来复用已有的密码过期机制,
    使用户下次登录即被强制要求修改密码。
    """
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="该账号已禁用,请先启用再重置密码")

    temp = _gen_temp_password()
    user.hashed_password = hash_password(temp)
    # 置为极早时间 → 同时触发"密码已过期"提示
    user.password_updated_at = datetime(2000, 1, 1)
    # 强制改密标志 → 后端拦截其余接口,直到用户改密成功
    user.must_change_password = True

    # 审计日志:只记录"谁重置了谁的密码",绝不记录密码内容
    log_op(db, current, "重置密码", target=f"成员#{user.id} {user.username}",
           detail="已生成临时密码,该用户下次登录需立即修改")
    db.commit()

    return {
        "ok": True,
        "username": user.username,
        "display_name": user.display_name,
        "temp_password": temp,
        "notice": "该临时密码仅显示这一次,关闭后无法再次查看,请立即转交给本人。",
    }


@router.get("/me/projects")
def my_projects(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ids = accessible_project_ids(db, current)
    if ids is None:
        projects = list(db.execute(select(Project).order_by(Project.id.desc())).scalars())
    else:
        projects = list(db.execute(select(Project).where(Project.id.in_(ids)).order_by(Project.id.desc())).scalars()) if ids else []
    return [
        {"id": p.id, "name": p.name, "description": p.description, "created_at": p.created_at.isoformat() if p.created_at else None}
        for p in projects
    ]
