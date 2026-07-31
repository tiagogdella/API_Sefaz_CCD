from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    cert_path: str
    cert_password: str
    cnpj: str
    uf_autor: str = "42"
    tp_amb: str = "1"

    class Config:
        env_file = ".env"

settings = Settings()
