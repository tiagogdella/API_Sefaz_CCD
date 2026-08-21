from pathlib import Path

from app.core.config import CertificateProfile
from app.services.cte_client import (
    _build_envelope_dist_nsu,
    extract_ch_cte,
    parse_max_nsu,
    parse_ult_nsu,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cte_proc_sample.xml"

FAKE_PROFILE = CertificateProfile(
    name="fake",
    cert_path="/nao/usado.pfx",
    cert_password="nao-usado",
    cnpj="82885781000103",
    uf_autor="42",
)


def load_sample() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_build_envelope_contains_correct_method_and_namespaces():
    envelope = _build_envelope_dist_nsu("000000000000000", FAKE_PROFILE)

    assert "cteDistDFeInteresse" in envelope
    assert "http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe" in envelope
    assert "http://www.portalfiscal.inf.br/cte" in envelope
    assert "<CNPJ>82885781000103</CNPJ>" in envelope
    assert "<cUFAutor>42</cUFAutor>" in envelope


def test_build_envelope_uses_ult_nsu_passed_in():
    envelope = _build_envelope_dist_nsu("000000000003648", FAKE_PROFILE)
    assert "<ultNSU>000000000003648</ultNSU>" in envelope


def test_extract_ch_cte_finds_key_in_full_document():
    chave = extract_ch_cte(load_sample())
    assert chave == "43260830800793000275570040000013051150732250"


def test_extract_ch_cte_returns_none_for_event_document():
    evento = '<procEventoCTe versao="4.00"><eventoCTe><infEvento Id="ID110200000001202608141234560000"></infEvento></eventoCTe></procEventoCTe>'
    assert extract_ch_cte(evento) is None


def test_parse_max_nsu_and_ult_nsu():
    response = "<retDistDFeInt><maxNSU>000000000004088</maxNSU><ultNSU>000000000003648</ultNSU></retDistDFeInt>"
    assert parse_max_nsu(response) == "000000000004088"
    assert parse_ult_nsu(response) == "000000000003648"
