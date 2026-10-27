from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import ProjectRole, User, user_projects
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# 被要求强制改密时,仍然允许访问的接口(否则用户无法完成改密)
# 只放行"看自己信息"和"改密码"这两个,其余一律拦截
PASSWORD_CHANGE_EXEMPT_PATHS = {
    "/api/auth/change-password",
    "/api/auth/me",
}


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = decode_access_token(token)
    if not user_id:
        raise credentials_exception
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        raise credentials_exception

    # 强制改密拦截:管理员重置密码后,除改密接口外一律拒绝,
    # 用 428 Precondition Required 与普通 403(权限不足)区分开,便于前端识别。
    if getattr(user, "must_change_password", False):
        path = request.url.path.rstrip("/") or "/"
        if path not in PASSWORD_CHANGE_EXEMPT_PATHS:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail="密码已被重置,请先修改密码后再继续操作",
            )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def accessible_project_ids(db: Session, user: User) -> list[int] | None:
    """返回当前用户可访问的项目ID列表;admin 返回 None 表示全部"""
    if user.role == "admin":
        return None
    rows = db.execute(select(user_projects.c.project_id).where(user_projects.c.user_id == user.id)).all()
    return [r[0] for r in rows]


def require_project_access(pid: int, db: Session, user: User) -> None:
    """校验当前用户是否有权访问某项目;无权则 403"""
    if user.role == "admin":
        return
    ids = accessible_project_ids(db, user)
    if ids is None or pid not in ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")


# ===================== RBAC 项目角色权限 =====================
ROLE_HIERARCHY = {"manager": 4, "test_lead": 3, "tester": 2, "viewer": 1}


def get_project_role(pid: int, db: Session, user: User) -> str | None:
    """获取用户在某项目中的角色;admin 返回 'manager'(最高权限)"""
    if user.role == "admin":
        return "manager"
    row = db.execute(
        select(ProjectRole.role).where(ProjectRole.user_id == user.id, ProjectRole.project_id == pid)
    ).scalar_one_or_none()
    return row


def require_project_role(pid: int, db: Session, user: User, min_role: str) -> str:
    """校验用户在项目中至少拥有 min_role 级别的角色"""
    role = get_project_role(pid, db, user)
    if role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不是该项目成员")
    if ROLE_HIERARCHY.get(role, 0) < ROLE_HIERARCHY.get(min_role, 0):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"需要 {min_role} 及以上权限,当前为 {role}")
    return role


def require_can_edit(pid: int, db: Session, user: User) -> None:
    """至少 tester 才能编辑(创建/修改用例、提交缺陷等)"""
    require_project_role(pid, db, user, "tester")


def require_can_manage(pid: int, db: Session, user: User) -> None:
    """至少 test_lead 才能管理(创建计划、审批用例、分配角色等)"""
    require_project_role(pid, db, user, "test_lead")
