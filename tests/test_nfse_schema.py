import pytest
from pydantic import ValidationError

from app.schemas.nfse import NFSeQueryRequest

# Chave real, validada contra producao na Fase 0 (ver TODONFSE.md) - nota de servico da della,
# prestador ALPHA CLEAN (Criciuma-SC), NSU 131.
VALID_NFSE_KEY = "42046082212942976000162000000000558126108153219373"


def test_accepts_valid_nfse_key():
    request = NFSeQueryRequest(accessKey=VALID_NFSE_KEY)
    assert request.access_key == VALID_NFSE_KEY


def test_rejects_nfe_key_44_digits():
    nfe_key = "42260845731998000132550010000016201009028410"
    with pytest.raises(ValidationError):
        NFSeQueryRequest(accessKey=nfe_key)


def test_rejects_non_numeric_key():
    with pytest.raises(ValidationError):
        NFSeQueryRequest(accessKey="a" * 50)


def test_rejects_wrong_length():
    with pytest.raises(ValidationError):
        NFSeQueryRequest(accessKey="123")
