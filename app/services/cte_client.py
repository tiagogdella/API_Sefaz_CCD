import requests
import requests_pkcs12
import re
import base64
import gzip
import logging

from app.services import rate_limiter
from app.services.sefaz_client import parse_status, SefazError, SefazNotFoundError
from app.core.config import CertificateProfile
from app.core.logging_config import log_event

# Confirmados por teste real contra producao em 21/08/2026 (ver TODOCTE.md) — namespace, versao e
# cUFAutor acertaram de primeira, sem precisar iterar.
URL = "https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx"
VERSION = "1.00"
NS_SCHEMA = "http://www.portalfiscal.inf.br/cte"
NS_WSDL = "http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe"
METHOD = "cteDistDFeInteresse"

# Trava de seguranca: no teste real, achar uma chave recente levou ~9 lotes de 50. 100 lotes
# (5000 NSUs) da bastante folga sem deixar rodar pra sempre num caso patologico.
MAX_NSU_BATCHES = 100

# cteProc completo observado no teste real tem varios KB. Abaixo disso e so um sinal fraco de
# alerta (ver nota sobre manifestacao no TODOCTE.md) — nao bloqueia o fluxo.
_MIN_EXPECTED_LENGTH = 500

_DOC_ZIP_PATTERN = re.compile(r'<docZip NSU="(\d+)"[^>]*>(.*?)</docZip>', re.DOTALL)
_MAX_NSU_PATTERN = re.compile(r"<maxNSU>(\d+)</maxNSU>")
_ULT_NSU_PATTERN = re.compile(r"<ultNSU>(\d+)</ultNSU>")
_CHAVE_PATTERN = re.compile(r'Id="CTe(\d{44})"')

logger = logging.getLogger("cte_client")


def _build_envelope_dist_nsu(ult_nsu: str, profile: CertificateProfile) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <{METHOD} xmlns="{NS_WSDL}">
      <cteDadosMsg>
        <distDFeInt xmlns="{NS_SCHEMA}" versao="{VERSION}">
          <tpAmb>1</tpAmb>
          <cUFAutor>{profile.uf_autor}</cUFAutor>
          <CNPJ>{profile.cnpj}</CNPJ>
          <distNSU>
            <ultNSU>{ult_nsu}</ultNSU>
          </distNSU>
        </distDFeInt>
      </cteDadosMsg>
    </{METHOD}>
  </soap12:Body>
</soap12:Envelope>"""


def query_dist_nsu(ult_nsu: str, profile: CertificateProfile) -> str:
    envelope = _build_envelope_dist_nsu(ult_nsu, profile)
    headers = {"Content-type": "application/soap+xml; charset=utf-8"}

    try:
        resp = requests_pkcs12.post(
            URL,
            data=envelope.encode("utf-8"),
            pkcs12_filename=profile.cert_path,
            pkcs12_password=profile.cert_password,
            headers=headers,
            timeout=30,
        )
    except (requests.exceptions.RequestException, FileNotFoundError, ValueError) as e:
        raise SefazError(f"Connection error with SEFAZ (CT-e): {e}") from e

    return resp.text


def extract_documents_with_nsu(xml_response: str) -> list[tuple[str, str]]:
    """Retorna [(NSU, documento_decodificado), ...] de cada docZip do lote.

    Nao reaproveita extract_documents() do sefaz_client.py porque essa descarta o NSU,
    que aqui e necessario pra paginar (ver TODOCTE.md, achado pos-Fase 0)."""
    documents = []
    for nsu, encoded in _DOC_ZIP_PATTERN.findall(xml_response):
        compressed = base64.b64decode(encoded)
        documents.append((nsu, gzip.decompress(compressed).decode("utf-8")))
    return documents


def parse_max_nsu(xml_response: str) -> str | None:
    match = _MAX_NSU_PATTERN.search(xml_response)
    return match.group(1) if match else None


def parse_ult_nsu(xml_response: str) -> str | None:
    match = _ULT_NSU_PATTERN.search(xml_response)
    return match.group(1) if match else None


def extract_ch_cte(document_xml: str) -> str | None:
    """Extrai a chave de acesso de um documento CT-e decodificado.

    Confirmado no teste real (21/08/2026): nao existe uma tag <chCTe> separada — a chave vem
    no atributo Id="CTe" + 44 digitos do elemento <infCte>, mesmo padrao do Id="NFe"+chave da
    NF-e. Documentos que sao eventos (schema="procEventoCTe_*.xsd") nao tem esse atributo e
    simplesmente nao dao match aqui — tratado como "nao e o documento procurado", nao como erro.
    """
    match = _CHAVE_PATTERN.search(document_xml)
    return match.group(1) if match else None


def get_full_document(access_key: str, profile: CertificateProfile) -> str:
    rate_limiter.check_cooldown(profile.cnpj, access_key)

    ult_nsu = "0".zfill(15)

    for batch_num in range(1, MAX_NSU_BATCHES + 1):
        raw_response = query_dist_nsu(ult_nsu, profile)
        c_stat, x_motivo = parse_status(raw_response)
        log_event(
            logger, logging.INFO, "cte distNSU batch result",
            access_key=access_key, profile=profile.name, batch=batch_num, ult_nsu=ult_nsu, c_stat=c_stat,
        )

        if c_stat in ("137", "640", "217"):
            rate_limiter.register_not_found(profile.cnpj, access_key)
            raise SefazNotFoundError(x_motivo)
        if c_stat != "138":
            raise SefazError(f"Unexpected cStat {c_stat}: {x_motivo}")

        for nsu, document in extract_documents_with_nsu(raw_response):
            if extract_ch_cte(document) != access_key:
                continue

            if len(document) < _MIN_EXPECTED_LENGTH:
                log_event(
                    logger, logging.WARNING, "cte document suspiciously short, might not be the full document",
                    access_key=access_key, profile=profile.name, nsu=nsu, length=len(document),
                )
            return document

        max_nsu = parse_max_nsu(raw_response)
        ult_nsu_resp = parse_ult_nsu(raw_response)

        if ult_nsu_resp is None:
            raise SefazError("Could not parse ultNSU from SEFAZ response (CT-e)")

        if max_nsu is not None and ult_nsu_resp >= max_nsu:
            rate_limiter.register_not_found(profile.cnpj, access_key)
            raise SefazNotFoundError(
                f"Access key {access_key} not found after paging through all available distNSU (maxNSU {max_nsu})"
            )

        ult_nsu = ult_nsu_resp

    rate_limiter.register_not_found(profile.cnpj, access_key)
    raise SefazNotFoundError(
        f"Access key {access_key} not found after {MAX_NSU_BATCHES} distNSU batches (safety limit reached)"
    )


def get_full_document_any_cnpj(access_key: str) -> tuple[str, str]:
    """Tries each configured certificate until one finds the document. Returns (xml, profile_name)."""
    from app.core.config import get_certificate_profiles

    last_error = None

    for profile in get_certificate_profiles():
        try:
            document = get_full_document(access_key, profile)
            return document, profile.name
        except (SefazNotFoundError, rate_limiter.RateLimitError) as e:
            log_event(
                logger, logging.INFO, "skipping profile, trying next (cte)",
                access_key=access_key, profile=profile.name, reason=str(e),
            )
            last_error = e
            continue

    log_event(logger, logging.WARNING, "cte access key not found for any cnpj", access_key=access_key)
    if isinstance(last_error, rate_limiter.RateLimitError):
        raise last_error
    raise SefazNotFoundError(f"CT-e access key {access_key} not found for any configured CNPJ")
