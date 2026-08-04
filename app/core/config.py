from dataclasses import dataclass

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    cert_della_path: str
    cert_della_password: str
    cert_della_cnpj: str
    cert_della_uf_autor: str = "42"

    cert_migra_path: str
    cert_migra_password: str
    cert_migra_cnpj: str
    cert_migra_uf_autor: str = "42"

    tp_amb: str = "1"

    class Config:
        env_file = ".env"


settings = Settings()


@dataclass
class CertificateProfile:
    name: str
    cert_path: str
    cert_password: str
    cnpj: str
    uf_autor: str


def get_certificate_profiles() -> list[CertificateProfile]:
    return [
        CertificateProfile(
            name="della",
            cert_path=settings.cert_della_path,
            cert_password=settings.cert_della_password,
            cnpj=settings.cert_della_cnpj,
            uf_autor=settings.cert_della_uf_autor,
        ),
        CertificateProfile(
            name="migra",
            cert_path=settings.cert_migra_path,
            cert_password=settings.cert_migra_password,
            cnpj=settings.cert_migra_cnpj,
            uf_autor=settings.cert_migra_uf_autor,
        ),
    ]
