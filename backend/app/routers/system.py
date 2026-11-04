from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..logger import log_op
from ..models import SystemConfig, User

router = APIRouter(prefix="/api/system", tags=["后台管理"])


class SystemConfigOut(BaseModel):
    session_timeout_minutes: int
    password_expire_days: int
    password_remind_days: int
    default_sit_days: int
    default_uat_days: int
    default_pre_days: int
    stage_remind_days: int


class SystemConfigUpdate(BaseModel):
    session_timeout_minutes: int | None = None
    password_expire_days: int | None = None
    password_remind_days: int | None = None
    default_sit_days: int | None = None
    default_uat_days: int | None = None
    default_pre_days: int | None = None
    stage_remind_days: int | None = None


def _get_or_create(db: Session) -> SystemConfig:
    cfg = db.execute(select(SystemConfig).limit(1)).scalar_one_or_none()
    if not cfg:
        cfg = SystemConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _dump(cfg: SystemConfig) -> dict:
    return {
        "session_timeout_minutes": cfg.session_timeout_minutes,
        "password_expire_days": cfg.password_expire_days,
        "password_remind_days": cfg.password_remind_days,
        "default_sit_days": cfg.default_sit_days,
        "default_uat_days": cfg.default_uat_days,
        "default_pre_days": cfg.default_pre_days,
        "stage_remind_days": cfg.stage_remind_days,
    }


@router.get("/config", response_model=SystemConfigOut)
def get_config(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _dump(_get_or_create(db))


@router.put("/config", response_model=SystemConfigOut, dependencies=[Depends(require_admin)])
def update_config(payload: SystemConfigUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    cfg = _get_or_create(db)
    if payload.stage_remind_days is not None and payload.stage_remind_days < 0:
        raise HTTPException(400, "阶段到期提醒天数不能为负数")
    for field in (
        "session_timeout_minutes", "password_expire_days", "password_remind_days",
        "default_sit_days", "default_uat_days", "default_pre_days", "stage_remind_days",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    log_op(db, current, "编辑", target="系统配置",
           detail=f"超时{cfg.session_timeout_minutes}分 密码{cfg.password_expire_days}天 提醒{cfg.password_remind_days}天 "
                  f"SIT{cfg.default_sit_days}天 UAT{cfg.default_uat_days}天 PRE{cfg.default_pre_days}天 到期提醒{cfg.stage_remind_days}天")
    return _dump(cfg)
