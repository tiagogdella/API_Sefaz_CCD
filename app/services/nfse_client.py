import requests
import requests_pkcs12
import base64
import gzip
import logging

from app.services import rate_limiter
from app.services.sefaz_client import SefazError, SefazNotFoundError
from app.core.config import CertificateProfile
from app.core.logging_config import log_event

# Confirmado por teste real contra producao em 02/10/2026 (ver TODONFSE.md) - URL e autenticacao
# mTLS com o certificado ja em uso (della) acertaram de primeira, sem credenciamento previo.
BASE_URL = "https://adn.nfse.gov.br/contribuintes"

# Trava de seguranca: no teste real, achar uma chave recente levou so 3 lotes de 50 (NSU 1->131).
# 100 lotes (5000 NSUs) da bastante folga, mesmo criterio do cte_client.py.
MAX_NSU_BATCHES = 100

logger = logging.getLogger("nfse_client")


def _decode_arquivo_xml(encoded: str) -> str:
    """ArquivoXml vem gzip+base64 (confirmado por teste real, mesmo padrao do docZip de NF-e/CT-e)."""
    compressed = base64.b64decode(encoded)
    return gzip.decompress(compressed).decode("utf-8")


def _find_in_lote(lote: list[dict], access_key: str) -> dict | None:
    """Acha, dentro de um lote de DistribuicaoNSU, o item cuja ChaveAcesso bate com a procurada.

    Diferente do CT-e: a ChaveAcesso ja vem como campo proprio em cada item (nao precisa
    decodificar o XML antes de comparar).
    """
    for item in lote:
        if item.get("ChaveAcesso") == access_key:
            return item
    return None


def _get_dfe_batch(nsu: str, profile: CertificateProfile) -> dict:
    url = f"{BASE_URL}/DFe/{nsu}"

    try:
        resp = requests_pkcs12.get(
            url,
            pkcs12_filename=profile.cert_path,
            pkcs12_password=profile.cert_password,
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except (requests.exceptions.RequestException, FileNotFoundError, ValueError) as e:
        raise SefazError(f"Connection error with ADN (NFS-e): {e}") from e

    try:
        return resp.json()
    except ValueError as e:
        raise SefazError(f"Could not parse ADN (NFS-e) response as JSON: {e}") from e


def get_full_document(access_key: str, profile: CertificateProfile) -> str:
    """Pagina GET /DFe/{NSU} a partir de NSU=0 ate achar a ChaveAcesso procurada.

    Nao existe consulta direta por chave nessa API (confirmado no Swagger oficial, ver
    TODONFSE.md) - mesma situacao do CT-e, so que aqui a ChaveAcesso ja vem como campo
    proprio em cada item do lote, sem precisar decodificar o XML antes de comparar.
    """
    rate_limiter.check_cooldown(profile.cnpj, access_key)

    nsu = "0"

    for batch_num in range(1, MAX_NSU_BATCHES + 1):
        data = _get_dfe_batch(nsu, profile)
        status = data.get("StatusProcessamento")
        log_event(
            logger, logging.INFO, "nfse DFe batch result",
            access_key=access_key, profile=profile.name, batch=batch_num, nsu=nsu, status=status,
        )

        if status == "NENHUM_DOCUMENTO_LOCALIZADO":
            rate_limiter.register_not_found(profile.cnpj, access_key)
            erros = data.get("Erros") or []
            motivo = erros[0].get("Descricao") if erros else "Nenhum documento localizado"
            raise SefazNotFoundError(motivo)

        if status != "DOCUMENTOS_LOCALIZADOS":
            raise SefazError(f"Unexpected StatusProcessamento {status}: {data.get('Erros')}")

        lote = data.get("LoteDFe") or []
        if not lote:
            rate_limiter.register_not_found(profile.cnpj, access_key)
            raise SefazNotFoundError(f"Access key {access_key} not found (empty LoteDFe)")

        found = _find_in_lote(lote, access_key)
        if found is not None:
            encoded = found.get("ArquivoXml")
            if not encoded:
                raise SefazError("Document found but ArquivoXml was empty")
            return _decode_arquivo_xml(encoded)

        # GET /DFe/{N} devolve itens com NSU > N (confirmado por teste real) - chamar de novo
        # com o maior NSU do lote nao repete nenhum item.
        nsu = str(max(item["NSU"] for item in lote))

    rate_limiter.register_not_found(profile.cnpj, access_key)
    raise SefazNotFoundError(
        f"Access key {access_key} not found after {MAX_NSU_BATCHES} DFe batches (safety limit reached)"
    )


def get_full_document_any_cnpj(access_key: str) -> tuple[str, str]:
    """Tries each configured certificate until one finds the document. Returns (xml, profile_name).

    Diferente de sefaz_client.py/cte_client.py: aqui tambem pulamos pro proximo perfil quando um
    certificado falha com SefazError generico (ex: certificado vencido), nao so NotFound/cooldown.
    Sem isso, um unico certificado com problema (caso real da migra vencida em 22/09/2026, ver
    TODONFSE.md) bloquearia a busca com 502 mesmo quando outro certificado configurado teria
    achado o documento. Se *nenhum* perfil funcionar, o ultimo SefazError real (nao NotFound) e
    repropagado no final, pra nao mascarar um problema de certificado como um 404 comum.
    """
    from app.core.config import get_certificate_profiles

    last_error: Exception | None = None

    for profile in get_certificate_profiles():
        try:
            document = get_full_document(access_key, profile)
            return document, profile.name
        except rate_limiter.RateLimitError as e:
            last_error = e
            continue
        except SefazNotFoundError as e:
            last_error = e
            continue
        except SefazError as e:
            log_event(
                logger, logging.WARNING, "profile failed with SefazError, trying next (nfse)",
                access_key=access_key, profile=profile.name, reason=str(e),
            )
            last_error = e
            continue

    log_event(logger, logging.WARNING, "nfse access key not found for any cnpj", access_key=access_key)
    if isinstance(last_error, rate_limiter.RateLimitError):
        raise last_error
    if isinstance(last_error, SefazError) and not isinstance(last_error, SefazNotFoundError):
        raise last_error
    raise SefazNotFoundError(f"NFS-e access key {access_key} not found for any configured CNPJ")
