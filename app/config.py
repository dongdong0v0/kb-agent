"""应用配置：全项目唯一的配置来源。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 单价（元 / 百万 token）—— 去 platform.deepseek.com 核对后改 .env

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 必填
    deepseek_api_key: SecretStr

    # 有默认值
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    request_timeout: float = 30.0
    max_tokens: int = 1024
    price_input_per_mtok: float = 2.0
    price_output_per_mtok: float = 8.0
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @field_validator("deepseek_api_key")
    @classmethod
    def _key_not_blank(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("DEEPSEEK_API_KEY 不能为空")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
