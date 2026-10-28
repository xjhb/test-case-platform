"""
配置迁移脚本：将 .env 配置推送到 Nacos
使用方法：python scripts/migrate_to_nacos.py
"""
import os
import sys
import json
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv

def load_env_config():
    """从 .env 文件加载配置"""
    env_path = Path(__file__).parent.parent / "backend" / ".env"
    if not env_path.exists():
        print(f"❌ .env 文件不存在: {env_path}")
        print("请先复制 .env.example 为 .env 并配置")
        sys.exit(1)
    
    load_dotenv(env_path)
    
    config = {
        "database_url": os.getenv("DATABASE_URL"),
        "secret_key": os.getenv("SECRET_KEY"),
        "algorithm": os.getenv("ALGORITHM", "HS256"),
        "access_token_expire_minutes": int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
        "cors_origins": os.getenv("CORS_ORIGINS", "http://localhost:5173"),
    }
    
    return config


def push_to_nacos(config):
    """将配置推送到 Nacos"""
    try:
        import nacos
    except ImportError:
        print("❌ 未安装 nacos-sdk-python")
        print("请运行: pip install nacos-sdk-python")
        sys.exit(1)
    
    # 从环境变量读取 Nacos 连接信息
    nacos_server = os.getenv("NACOS_SERVER")
    nacos_namespace = os.getenv("NACOS_NAMESPACE", "")
    nacos_data_id = os.getenv("NACOS_DATA_ID", "testmanage")
    nacos_group = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
    nacos_username = os.getenv("NACOS_USERNAME", "")
    nacos_password = os.getenv("NACOS_PASSWORD", "")
    
    if not nacos_server:
        print("❌ 未配置 NACOS_SERVER")
        print("请在 .env 文件中配置 NACOS_SERVER")
        sys.exit(1)
    
    print(f"📡 连接 Nacos: {nacos_server}")
    print(f"📦 Data ID: {nacos_data_id}, Group: {nacos_group}")
    
    try:
        client = nacos.NacosClient(
            nacos_server,
            namespace=nacos_namespace,
            username=nacos_username,
            password=nacos_password,
        )
        
        # 转换为 JSON 格式
        config_json = json.dumps(config, indent=2, ensure_ascii=False)
        
        # 发布配置
        result = client.publish_config(nacos_data_id, nacos_group, config_json)
        
        if result:
            print("✅ 配置已成功推送到 Nacos")
            print("\n配置内容:")
            print("-" * 60)
            # 隐藏敏感信息
            safe_config = config.copy()
            if "database_url" in safe_config:
                safe_config["database_url"] = "mysql+pymysql://***:***@***"
            if "secret_key" in safe_config:
                safe_config["secret_key"] = "***"
            print(json.dumps(safe_config, indent=2, ensure_ascii=False))
            print("-" * 60)
            return True
        else:
            print("❌ 推送配置失败")
            return False
            
    except Exception as e:
        print(f"❌ 连接 Nacos 失败: {e}")
        sys.exit(1)


def main():
    print("=" * 60)
    print("配置迁移工具：.env → Nacos")
    print("=" * 60)
    print()
    
    # 加载 .env 配置
    print("📖 读取 .env 配置...")
    config = load_env_config()
    print(f"   已读取 {len(config)} 项配置")
    print()
    
    # 推送到 Nacos
    print("📤 推送到 Nacos...")
    success = push_to_nacos(config)
    
    if success:
        print()
        print("🎉 迁移完成！")
        print()
        print("下一步：")
        print("1. 启动后端服务: cd backend && python -m uvicorn app.main:app --reload")
        print("2. 后端会自动从 Nacos 加载配置")
        print("3. 可以在 Nacos 控制台查看和修改配置")
    else:
        print()
        print("❌ 迁移失败，请检查 Nacos 连接配置")
        sys.exit(1)


if __name__ == "__main__":
    main()
