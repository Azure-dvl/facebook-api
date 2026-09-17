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
    # Supabase (y la mayoria de Postgres gestionados) exigen SSL.
    # En local dejalo en false; en Supabase true.
    DB_SSL: bool = False

    ENCRYPTION_KEY: str = ""

    # URL publica bajo la cual se accede a la API (la que van en los links).
    # Por defecto localhost. Para un servidor remoto configurala con el host/IP
    # alcanzable (ej: "https://api.midominio.com" o "http://192.168.1.5:8000").
    # PENSA: si la dejas vacia se usa la ip/host detectada del request.
    APP_PUBLIC_URL: str = ""

    @property
    def DATABASE_URL(self) -> str:
        url = (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
        return f"{url}?sslmode=require" if self.DB_SSL else url

    @property
    def DATABASE_URL_SYNC(self) -> str:
        url = (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
        return f"{url}?sslmode=require" if self.DB_SSL else url

    @property
    def PUBLIC_BASE_URL(self) -> str:
        if self.APP_PUBLIC_URL:
            return self.APP_PUBLIC_URL.rstrip("/")
        return f"http://localhost:{self.APP_PORT}"


settings = Settings()
