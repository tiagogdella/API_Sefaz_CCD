import pytest
from pydantic import ValidationError

from app.schemas.cte import CTeQueryRequest

VALID_CTE_KEY = "43260830800793000275570040000013051150732250"  # modelo 57, validado na Fase 0


def test_accepts_valid_cte_key_model_57():
    request = CTeQueryRequest(accessKey=VALID_CTE_KEY)
    assert request.access_key == VALID_CTE_KEY


def test_accepts_cte_os_model_67():
    # mesma chave com o modelo trocado pra 67 (CT-e OS), so pra testar a aceitacao do modelo -
    # digito verificador nao e checado por esse schema, so o formato
    key = VALID_CTE_KEY[:20] + "67" + VALID_CTE_KEY[22:]
    request = CTeQueryRequest(accessKey=key)
    assert request.access_key == key


def test_rejects_nfe_key_model_55():
    nfe_key = "42260845731998000132550010000016201009028410"
    with pytest.raises(ValidationError):
        CTeQueryRequest(accessKey=nfe_key)


def test_rejects_non_numeric_key():
    with pytest.raises(ValidationError):
        CTeQueryRequest(accessKey="a" * 44)


def test_rejects_wrong_length():
    with pytest.raises(ValidationError):
        CTeQueryRequest(accessKey="123")
