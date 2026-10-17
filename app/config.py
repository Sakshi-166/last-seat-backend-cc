from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "The Last Seat API"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/lastseat"
    hold_minutes: int = 5
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
