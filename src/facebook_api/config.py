from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    APP_NAME: str = "Facebook API"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = False

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "fb_user"
    DB_PASSWORD: str = ""
    DB_NAME: str = "facebook_api"

    ENCRYPTION_KEY: str = ""

    # URL publica bajo la cual se accede a la API (la que van en los links).
    # Por defecto localhost. Para un servidor remoto configurala con el host/IP
    # alcanzable (ej: "https://api.midominio.com" o "http://192.168.1.5:8000").
    # PENSA: si la dejas vacia se usa la ip/host detectada del request.
    APP_PUBLIC_URL: str = ""

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def PUBLIC_BASE_URL(self) -> str:
        if self.APP_PUBLIC_URL:
            return self.APP_PUBLIC_URL.rstrip("/")
        return f"http://localhost:{self.APP_PORT}"


settings = Settings()
