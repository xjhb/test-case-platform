"""初始化系统角色定义表，创建默认的四个角色"""
import sys
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select
from app.database import SessionLocal, engine
from app.models import RoleDefinition, Base
from app.config import settings

def init_roles():
    """创建 role_definitions 表并初始化默认角色"""
    print(f"使用数据库配置: {settings.database_url.replace(settings.database_url.split('@')[0].split(':')[1], '***')}")
    
    # 创建表
    Base.metadata.create_all(bind=engine, tables=[RoleDefinition.__table__])

    db = SessionLocal()
    try:
        # 检查是否已有角色定义
        stmt = select(RoleDefinition)
        result = db.execute(stmt)
        roles = result.scalars().all()
        
        if len(roles) > 0:
            print(f"已存在 {len(roles)} 个角色定义，跳过初始化")
            return

        # 创建默认的四个系统角色
        default_roles = [
            {
                "role_code": "manager",
                "role_name": "项目经理",
                "description": "项目管理员，拥有项目的全部管理权限",
                "is_system": True,
                "sort_order": 1,
            },
            {
                "role_code": "test_lead",
                "role_name": "测试负责人",
                "description": "测试经理/测试组长，负责测试计划和用例管理",
                "is_system": True,
                "sort_order": 2,
            },
            {
                "role_code": "tester",
                "role_name": "测试员",
                "description": "测试执行人员，负责执行测试用例和提交缺陷",
                "is_system": True,
                "sort_order": 3,
            },
            {
                "role_code": "viewer",
                "role_name": "只读用户",
                "description": "仅可查看项目信息，无编辑权限",
                "is_system": True,
                "sort_order": 4,
            },
        ]

        for role_data in default_roles:
            role = RoleDefinition(**role_data)
            db.add(role)
            print(f"创建角色: {role_data['role_code']} - {role_data['role_name']}")

        db.commit()
        print("角色定义初始化完成！")

    except Exception as e:
        db.rollback()
        print(f"初始化失败: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_roles()