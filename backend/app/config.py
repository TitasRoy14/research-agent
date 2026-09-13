from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openrouter_api_key: str
    openrouter_model: str = "inclusionai/ling-3.0-flash-vl:free"
    serper_api_key: str
    serpapi_api_key: str

    research_max_subqueries: int = 3
    research_max_sources_to_fetch: int = 6
    research_max_sources_in_answer: int = 8

    # Per-provider network settings
    http_timeout_seconds: float = 10.0
    max_retries: int = 3

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
