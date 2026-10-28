from pydantic_settings import BaseSettings, SettingsConfigDict
import os
import json


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://user:password@localhost:3306/dbname?charset=utf8mb4"
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    
    # Nacos 配置
    nacos_server: str = ""
    nacos_namespace: str = ""
    nacos_data_id: str = "testmanage"
    nacos_group: str = "DEFAULT_GROUP"
    nacos_username: str = ""
    nacos_password: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 如果配置了 Nacos，从 Nacos 加载配置
        if self.nacos_server:
            self._load_from_nacos()
    
    def _load_from_nacos(self):
        """从 Nacos 配置中心加载配置"""
        try:
            import nacos
            
            client = nacos.NacosClient(
                self.nacos_server,
                namespace=self.nacos_namespace,
                username=self.nacos_username,
                password=self.nacos_password,
            )
            
            config_text = client.get_config(self.nacos_data_id, self.nacos_group)
            if config_text:
                config = json.loads(config_text)
                
                # 覆盖本地配置
                if "database_url" in config:
                    self.database_url = config["database_url"]
                if "secret_key" in config:
                    self.secret_key = config["secret_key"]
                if "algorithm" in config:
                    self.algorithm = config["algorithm"]
                if "access_token_expire_minutes" in config:
                    self.access_token_expire_minutes = config["access_token_expire_minutes"]
                if "cors_origins" in config:
                    self.cors_origins = config["cors_origins"]
                
                print(f"✅ 已从 Nacos 加载配置: {self.nacos_data_id}")
            else:
                print(f"⚠️ Nacos 中未找到配置: {self.nacos_data_id}，使用本地 .env 配置")
        except ImportError:
            print("⚠️ 未安装 nacos-sdk-python，使用本地 .env 配置")
        except Exception as e:
            print(f"⚠️ 从 Nacos 加载配置失败: {e}，使用本地 .env 配置")


settings = Settings()
