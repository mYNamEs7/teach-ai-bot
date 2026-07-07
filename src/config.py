from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    database_url: str
    redis_url: str
    openrouter_api_key: str
    payment_provider_token: str = ""
    payment_stars_token: str = ""
    admin_ids: List[int] = []
    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_contact: str = "@admin_username"
    free_daily_limit: int = 5
    monthly_price_stars: int = 50
    monthly_price_rub: int = 199
    three_month_price_stars: int = 120
    three_month_price_rub: int = 499
    redis_context_max: int = 20
    redis_cleanup_days: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
