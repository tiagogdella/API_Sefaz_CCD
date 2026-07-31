import requests
import requests_pkcs12
import re

from app.core.config import settings

URL ="https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
VERSION = "1.01"
_C_STAT_PATTERN = re.compile(r"<cStat>(\d+)</cStat>")
_X_MOTIVO_PATTERN = re.compile(r"<xMotivo>(.*?)</xMotivo>")

class SefazError(Exception):
    """Connection/network error talking to SEFAZ (not a business rejection — that comes in cStat)."""

def _build_envelope(access_key: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="{VERSION}">
          <tpAmb>{settings.tp_amb}</tpAmb>
          <cUFAutor>{settings.uf_autor}</cUFAutor>
          <CNPJ>{settings.cnpj}</CNPJ>
          <consChNFe>
            <chNFe>{access_key}</chNFe>
          </consChNFe>
        </distDFeInt>
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>"""

def query_by_access_key(access_key: str) -> str:
    envelope = _build_envelope(access_key)
    headers = {"Content-type": "application/soap+xml; charset=utf-8"}

    try:
        resp = requests_pkcs12.post(
            URL,
            data=envelope.encode("utf-8"),
            pkcs12_filename=settings.cert_path,
            pkcs12_password=settings.cert_password,
            headers=headers,
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        raise SefazError(f"Connection error with SEFAZ: {e}") from e

    return resp.text

def parse_status(xml_response:str) -> tuple[str, str]:
    c_stat_match = _C_STAT_PATTERN.search(xml_response)
    x_motivo_match = _X_MOTIVO_PATTERN.search(xml_response)

    if not c_stat_match or not x_motivo_match:
        raise SefazError("Could not parse cStat/xMotivo from SEFAZ response")

    return c_stat_match.group(1), x_motivo_match.group(1)