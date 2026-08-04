from pathlib import Path

from app.services.nfe_parser import parse_nfe_proc

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_proc_sample.xml"


def load_sample() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_nfe_proc_extracts_supplier():
    parsed = parse_nfe_proc(load_sample(), "della")

    assert parsed.supplier_cnpj == "72472038000178"
    assert parsed.supplier_name == "UNIVERSAL INFORMATICA LTDA"
    assert parsed.certificate_profile == "della"


def test_parse_nfe_proc_extracts_total():
    parsed = parse_nfe_proc(load_sample(), "della")

    assert parsed.total_amount == 1055.57


def test_parse_nfe_proc_extracts_items():
    parsed = parse_nfe_proc(load_sample(), "della")

    assert len(parsed.items) == 2
    first = parsed.items[0]
    assert first.code == "22426"
    assert first.quantity == 6.0
    assert first.unit_price == 138.5
    assert first.total_price == 831.0
