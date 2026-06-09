"""
OpenAI_Chat - 已精简 (2026-06 清理)

只保留 system_message / user_message / assistant_message 三个 message 包装器
已删除:
  - submit_prompt (70 行, MyVanna 用 self.client 直调, 不走 submit_prompt)
  - api_type/api_base/api_version 已废弃配置检查
"""


from openai import OpenAI

from ..base import VannaBase


class OpenAI_Chat(VannaBase):
    def __init__(self, client=None, config=None):
        VannaBase.__init__(self, config=config)

        self.temperature = 0.7
        if config and "temperature" in config:
            self.temperature = config["temperature"]

        if client is not None:
            self.client = client
        elif config and "api_key" in config:
            self.client = OpenAI(api_key=config["api_key"])
        else:
            import os
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def system_message(self, message: str) -> dict:
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> dict:
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> dict:
        return {"role": "assistant", "content": message}
