import base64
import gzip

from app.services.nfse_client import _decode_arquivo_xml, _find_in_lote

SAMPLE_XML = '<NFSe versao="1.01"><infNFSe Id="NFS00000000000000000000000000000000000000000000000000"></infNFSe></NFSe>'


def _encode(xml: str) -> str:
    return base64.b64encode(gzip.compress(xml.encode("utf-8"))).decode("ascii")


def test_decode_arquivo_xml_roundtrip():
    encoded = _encode(SAMPLE_XML)
    assert _decode_arquivo_xml(encoded) == SAMPLE_XML


def test_find_in_lote_finds_matching_chave():
    lote = [
        {"NSU": 1, "ChaveAcesso": "chave-a", "ArquivoXml": "..."},
        {"NSU": 2, "ChaveAcesso": "chave-b", "ArquivoXml": "..."},
    ]
    found = _find_in_lote(lote, "chave-b")
    assert found is not None
    assert found["NSU"] == 2


def test_find_in_lote_returns_none_when_not_present():
    lote = [{"NSU": 1, "ChaveAcesso": "chave-a", "ArquivoXml": "..."}]
    assert _find_in_lote(lote, "chave-z") is None


def test_find_in_lote_handles_empty_lote():
    assert _find_in_lote([], "chave-a") is None
