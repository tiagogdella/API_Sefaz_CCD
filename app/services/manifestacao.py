from datetime import datetime

import xmlsec
import requests
import requests_pkcs12
import re

from app.services.sefaz_client import SefazError
from lxml import etree
from app.core.config import settings, CertificateProfile
from app.services.certificate import load_certificate

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
AWARENESS_EVENT_CODE = "210210"
RECEPCAO_EVENTO_URL = "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"
RECEPCAO_EVENTO_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4"
_C_STAT_PATTERN = re.compile(r"<cStat>(\d+)</cStat>")
_X_MOTIVO_PATTERN = re.compile(r"<xMotivo>(.*?)</xMotivo>")
SUCCESS_CSTAT = "135"


def _tag(name: str) -> str:
    return f"{{{NFE_NS}}}{name}"


def build_awareness_event(access_key: str, profile: CertificateProfile, sequence: int = 1) -> tuple[etree._Element, str]:
    event_id = f"ID{AWARENESS_EVENT_CODE}{access_key}{sequence:02d}"
    event_datetime = datetime.now().astimezone().isoformat(timespec="seconds")

    env_evento = etree.Element(_tag("envEvento"), nsmap={None: NFE_NS})
    env_evento.set("versao", "1.00")

    id_lote = etree.SubElement(env_evento, _tag("idLote"))
    id_lote.text = "1"

    evento = etree.SubElement(env_evento, _tag("evento"))
    evento.set("versao", "1.00")

    inf_evento = etree.SubElement(evento, _tag("infEvento"))
    inf_evento.set("Id", event_id)

    etree.SubElement(inf_evento, _tag("cOrgao")).text = "91"
    etree.SubElement(inf_evento, _tag("tpAmb")).text = settings.tp_amb
    etree.SubElement(inf_evento, _tag("CNPJ")).text = profile.cnpj
    etree.SubElement(inf_evento, _tag("chNFe")).text = access_key
    etree.SubElement(inf_evento, _tag("dhEvento")).text = event_datetime
    etree.SubElement(inf_evento, _tag("tpEvento")).text = AWARENESS_EVENT_CODE
    etree.SubElement(inf_evento, _tag("nSeqEvento")).text = str(sequence)
    etree.SubElement(inf_evento, _tag("verEvento")).text = "1.00"

    det_evento = etree.SubElement(inf_evento, _tag("detEvento"))
    det_evento.set("versao", "1.00")
    etree.SubElement(det_evento, _tag("descEvento")).text = "Ciencia da Operacao"

    signature_node = xmlsec.template.create(evento, xmlsec.Transform.C14N, xmlsec.Transform.RSA_SHA1)
    evento.append(signature_node)

    reference = xmlsec.template.add_reference(signature_node, xmlsec.Transform.SHA1, uri=f"#{event_id}")
    xmlsec.template.add_transform(reference, xmlsec.Transform.ENVELOPED)
    xmlsec.template.add_transform(reference, xmlsec.Transform.C14N)

    key_info = xmlsec.template.ensure_key_info(signature_node)
    xmlsec.template.add_x509_data(key_info)

    private_key_pem, certificate_pem = load_certificate(profile)

    key = xmlsec.Key.from_memory(private_key_pem, xmlsec.KeyFormat.PEM)
    key.load_cert_from_memory(certificate_pem, xmlsec.KeyFormat.CERT_PEM)

    ctx = xmlsec.SignatureContext()
    ctx.key = key
    xmlsec.tree.add_ids(evento, ["Id"])
    ctx.sign(signature_node)

    return env_evento, event_id


def send_awareness_event(access_key: str, profile: CertificateProfile, sequence: int = 1) -> tuple[str, str]:
    env_evento, _ = build_awareness_event(access_key, profile, sequence)
    evento_xml = etree.tostring(env_evento).decode()

    envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Header>
    <nfeCabecMsg xmlns="{RECEPCAO_EVENTO_NS}">
      <cUF>{profile.uf_autor}</cUF>
      <versaoDados>1.00</versaoDados>
    </nfeCabecMsg>
  </soap12:Header>
  <soap12:Body>
    <nfeDadosMsg xmlns="{RECEPCAO_EVENTO_NS}">
      {evento_xml}
    </nfeDadosMsg>
  </soap12:Body>
</soap12:Envelope>"""

    headers = {"Content-Type": "application/soap+xml; charset=utf-8"}

    try:
        resp = requests_pkcs12.post(
            RECEPCAO_EVENTO_URL,
            data=envelope.encode("utf-8"),
            pkcs12_filename=profile.cert_path,
            pkcs12_password=profile.cert_password,
            headers=headers,
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        raise SefazError(f"Connection error with SEFAZ (manifestacao): {e}") from e

    c_stat_matches = _C_STAT_PATTERN.findall(resp.text)
    x_motivo_matches = _X_MOTIVO_PATTERN.findall(resp.text)

    if not c_stat_matches or not x_motivo_matches:
        raise SefazError(f"Could not parse cStat/xMotivo from manifestacao response. Raw: {resp.text[:1500]}")

    c_stat = c_stat_matches[-1]
    x_motivo = x_motivo_matches[-1]

    if c_stat != SUCCESS_CSTAT:
        raise SefazError(f"Manifestacao rejected or incomplete (cStat={c_stat}): {x_motivo}")

    return c_stat, x_motivo
