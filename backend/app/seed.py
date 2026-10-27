from sqlalchemy import select

from .database import SessionLocal
from .models import User
from .security import hash_password

# 默认管理员账号(首次启动时自动创建,生产环境请尽快修改密码)
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


def seed_admin() -> None:
    db = SessionLocal()
    try:
        exists = db.execute(select(User).where(User.username == DEFAULT_ADMIN_USER)).scalar_one_or_none()
        if not exists:
            db.add(
                User(
                    username=DEFAULT_ADMIN_USER,
                    hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
                    display_name="管理员",
                    role="admin",
                )
            )
            db.commit()
            print(f"[seed] 已创建默认管理员: {DEFAULT_ADMIN_USER} / {DEFAULT_ADMIN_PASSWORD}")
    finally:
        db.close()
