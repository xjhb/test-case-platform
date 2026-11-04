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

    # ---- 外部集成凭据(全部可选,未配置的通道接口返回 503) ----
    # 只允许通过 .env 或 Nacos 注入,严禁写入代码与仓库
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_ssl: bool = True

    dingtalk_webhook_url: str = ""
    dingtalk_secret: str = ""
    wecom_webhook_url: str = ""
    feishu_webhook_url: str = ""

    jenkins_base_url: str = ""
    jenkins_user: str = ""
    jenkins_token: str = ""
    gitlab_base_url: str = ""
    gitlab_token: str = ""
    github_token: str = ""

    jira_base_url: str = ""
    jira_user: str = ""
    jira_token: str = ""
    jira_project_key: str = ""
    zentao_base_url: str = ""
    zentao_account: str = ""
    zentao_password: str = ""
    zentao_product_id: str = ""

    # 外部系统回调的共享密钥(X-Webhook-Token);为空则回调只接受平台登录令牌
    webhook_secret: str = ""
    # 本平台对外地址,用于通知里的跳转链接
    platform_base_url: str = ""
    # 关闭后站内信照写,不再调用邮件/群机器人等外部通道
    notify_external_enabled: bool = True

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

                # 覆盖本地配置:凡是模型上声明过的字段都允许从 Nacos 下发
                applied = 0
                for key, value in config.items():
                    if key in type(self).model_fields:
                        setattr(self, key, value)
                        applied += 1

                print(f"[OK] 已从 Nacos 加载配置: {self.nacos_data_id}, 覆盖 {applied} 项")
            else:
                print(f"[WARN] Nacos 中未找到配置: {self.nacos_data_id}，使用本地 .env 配置")
        except ImportError:
            print("[WARN] 未安装 nacos-sdk-python，使用本地 .env 配置")
        except Exception as e:
            print(f"[WARN] 从 Nacos 加载配置失败: {e}，使用本地 .env 配置")


settings = Settings()
