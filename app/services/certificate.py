from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

from app.core.config import CertificateProfile


def load_certificate(profile: CertificateProfile) -> tuple[bytes, bytes]:
    with open(profile.cert_path, "rb") as f:
        pfx_data = f.read()

    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        pfx_data, profile.cert_password.encode()
    )

    private_key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption(),
    )
    certificate_pem = certificate.public_bytes(encoding=Encoding.PEM)

    return private_key_pem, certificate_pem
