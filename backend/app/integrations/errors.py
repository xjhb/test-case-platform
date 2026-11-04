"""集成层通用异常:未配置与远端失败在接口上分别对应 503 与 502"""


class IntegrationError(Exception):
    """远端系统返回失败或不可达"""

    def __init__(self, channel: str, message: str):
        self.channel = channel
        super().__init__(f"{channel}: {message}")


class NotConfigured(IntegrationError):
    """凭据缺失,该通道不可用"""

    def __init__(self, channel: str, missing_keys: list[str]):
        self.missing_keys = missing_keys
        super().__init__(channel, f"未配置,缺少环境变量 {', '.join(missing_keys)}")
