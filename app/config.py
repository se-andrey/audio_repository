from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    db_url: str = Field(..., env='DATABASE_URL')
    host_url: str = Field(..., env='HOST_URL')


settings = Settings()
