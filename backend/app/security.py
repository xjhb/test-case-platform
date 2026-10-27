from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import select

from .config import settings
from .database import SessionLocal


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def get_session_timeout() -> int:
    """从数据库读取超时配置,默认30分钟"""
    try:
        db = SessionLocal()
        from .models import SystemConfig
        cfg = db.execute(select(SystemConfig).limit(1)).scalar_one_or_none()
        db.close()
        if cfg:
            return cfg.session_timeout_minutes
    except Exception:
        pass
    return 30


def create_access_token(subject: str | int, timeout_minutes: int | None = None) -> str:
    minutes = timeout_minutes if timeout_minutes is not None else get_session_timeout()
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
