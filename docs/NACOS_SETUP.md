# Nacos 配置中心部署指南

> **当前使用版本: Nacos 2.4.3**
> 升级 Nacos 时请注意版本兼容性，参考 [Nacos 升级指南](https://nacos.io/docs/latest/upgrading/)

## 概述

测管平台已集成 Nacos 配置中心，支持将数据库连接、JWT密钥等敏感配置集中管理。

## 前置条件

- Java 8 或更高版本 (JDK)
- MySQL 8.0 (Nacos 持久化存储，可选，默认使用内嵌 Derby)

## 第一步：安装 Java

### Windows

1. 下载 JDK: https://adoptium.net/
2. 选择 JDK 17 (LTS 版本)
3. 安装后配置环境变量:
   ```
   JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-17.x.x
   PATH=%JAVA_HOME%\bin;%PATH%
   ```
4. 验证: `java -version`

## 第二步：下载 Nacos

1. 访问: https://github.com/alibaba/nacos/releases
2. 下载最新稳定版 `nacos-server-2.x.x.zip`
3. 解压到任意目录，例如: `D:\nacos`

## 第三步：启动 Nacos

### 单机模式（开发环境）

```bash
# Windows
cd D:\nacos\bin
startup.cmd -m standalone

# Linux/Mac
cd /opt/nacos/bin
sh startup.sh -m standalone
```

### 验证启动

访问控制台: http://localhost:8848/nacos
- 默认账号: nacos
- 默认密码: nacos

## 第四步：配置 .env

编辑 `backend/.env`，添加 Nacos 连接信息:

```env
# Nacos 配置
NACOS_SERVER=localhost:8848
NACOS_NAMESPACE=
NACOS_DATA_ID=testmanage
NACOS_GROUP=DEFAULT_GROUP
NACOS_USERNAME=nacos
NACOS_PASSWORD=nacos

# 其他配置（首次迁移时需要）
DATABASE_URL=mysql+pymysql://root:your_password@localhost:3306/testmanage?charset=utf8mb4
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

## 第五步：迁移配置到 Nacos

```bash
cd D:\Qoder
python scripts/migrate_to_nacos.py
```

成功后，配置会以 JSON 格式存储在 Nacos 中。

## 第六步：验证

1. 在 Nacos 控制台 → 配置管理 → 配置列表 中查看 `testmanage` 配置
2. 启动后端: `cd backend && python -m uvicorn app.main:app --reload`
3. 查看控制台输出，应显示 `✅ 已从 Nacos 加载配置: testmanage`

## 配置格式说明

Nacos 中存储的配置为 JSON 格式:

```json
{
  "database_url": "mysql+pymysql://user:pass@localhost:3306/testmanage?charset=utf8mb4",
  "secret_key": "your-jwt-secret-key",
  "algorithm": "HS256",
  "access_token_expire_minutes": 1440,
  "cors_origins": "http://localhost:5173,http://127.0.0.1:5173"
}
```

## 动态配置更新

Nacos 支持运行时修改配置，后端重启后会自动加载最新配置。

如需支持热更新（不重启），可在 config.py 中添加 Nacos 监听器:

```python
def add_nacos_listener(self):
    client.add_config_watcher(
        self.nacos_data_id,
        self.nacos_group,
        self._on_config_change
    )

def _on_config_change(self, config_info):
    # 热更新逻辑
    pass
```

## 生产环境建议

1. **使用集群模式**: 至少 3 节点
2. **开启鉴权**: 修改 `nacos.core.auth.enabled=true`
3. **使用 MySQL 持久化**: 配置 `application.properties` 中的数据库连接
4. **命名空间隔离**: 为不同环境（dev/test/prod）创建独立 namespace
5. **配置加密**: 敏感字段使用 Nacos 配置加密插件

## 故障排查

| 问题 | 解决方案 |
|------|---------|
| Nacos 启动失败 | 检查 Java 版本 >= 8，端口 8848/9848/9849 未被占用 |
| 连接 Nacos 失败 | 检查 NACOS_SERVER 地址，防火墙是否放行 |
| 配置未加载 | 检查 Data ID 和 Group 是否匹配 |
| 推送配置失败 | 检查 Nacos 用户名密码是否正确 |
