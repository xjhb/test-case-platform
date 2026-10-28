"""添加用户个人信息字段 (email, phone)"""
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))
os.chdir(str(backend_dir))

from sqlalchemy import text
from app.database import engine

def add_fields():
    """添加 email 和 phone 字段到 users 表"""
    print("正在添加用户个人信息字段...")
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'users' AND COLUMN_NAME IN ('email', 'phone')
        """))
        existing = [row[0] for row in result]
        
        if 'email' not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(128) DEFAULT ''"))
            print("[OK] 添加 email 字段")
        
        if 'phone' not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(32) DEFAULT ''"))
            print("[OK] 添加 phone 字段")
        
        if 'email' in existing and 'phone' in existing:
            print("字段已存在，无需添加")
        
        conn.commit()
    
    print("数据库字段添加完成!")

if __name__ == "__main__":
    add_fields()
