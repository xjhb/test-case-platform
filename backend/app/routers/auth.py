from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..logger import log_op
from ..models import SystemConfig, User
from ..schemas import ChangePasswordRequest, LoginRequest, Token, UserCreate, UserOut
from ..security import create_access_token, get_session_timeout, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _password_status(db: Session, user: User) -> dict:
    """检查密码到期状态"""
    cfg = db.execute(select(SystemConfig).limit(1)).scalar_one_or_none()
    expire_days = cfg.password_expire_days if cfg else 30
    remind_days = cfg.password_remind_days if cfg else 10

    if not user.password_updated_at:
        return {"password_expiring": False, "password_days_left": None, "password_expired": False}

    now = datetime.now(timezone.utc)
    pwd_time = user.password_updated_at
    if pwd_time.tzinfo is None:
        pwd_time = pwd_time.replace(tzinfo=timezone.utc)

    days_passed = (now - pwd_time).days
    days_left = expire_days - days_passed

    expired = days_left <= 0
    expiring = 0 < days_left <= remind_days

    return {
        "password_expiring": expiring,
        "password_days_left": max(days_left, 0),
        "password_expired": expired,
    }


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        log_op(db, None, "登录", target=payload.username, detail="失败:用户名或密码错误",
               ip=request.client.host if request.client else "")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        log_op(db, user, "登录", detail="失败:账号已禁用",
               ip=request.client.host if request.client else "")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

    token = create_access_token(user.id)
    pwd_status = _password_status(db, user)
    log_op(db, user, "登录", detail="成功", ip=request.client.host if request.client else "")
    return Token(
        access_token=token,
        role=user.role,
        display_name=user.display_name,
        must_change_password=bool(getattr(user, "must_change_password", False)),
        **pwd_status,
    )


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if not verify_password(payload.old_password, current.hashed_password):
        raise HTTPException(status_code=400, detail="原密码错误")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")
    current.hashed_password = hash_password(payload.new_password)
    current.password_updated_at = datetime.now(timezone.utc)
    # 改密成功 → 解除强制改密拦截
    current.must_change_password = False
    db.commit()
    log_op(db, current, "编辑", target="密码修改", detail=f"用户#{current.id}")
    return {"ok": True}


@router.post("/register", response_model=UserOut)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    exists = db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
