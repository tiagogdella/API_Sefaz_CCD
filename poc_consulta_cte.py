import os
import sys
import re
import time
import base64
import gzip
import requests
import requests_pkcs12

CERT_PATH = os.environ.get("CERT_PATH")
CERT_PASSWORD = os.environ.get("CERT_PASSWORD")
CNPJ = os.environ.get("CNPJ", "82885781000103")
UF_AUTOR = os.environ.get("UF_AUTOR", "42")  # hipotese: mesmo valor da NF-e — item em aberto no TODOCTE.md
TP_AMB = os.environ.get("TP_AMB", "1")  # 1 = producao
ULT_NSU = os.environ.get("ULT_NSU", "000000000000000")
TARGET_CHAVE = os.environ.get("TARGET_CHAVE", "43260830800793000275570040000012651374168806")
MAX_LOTES = int(os.environ.get("MAX_LOTES", "20"))  # trava de seguranca, nao deixa rodar pra sempre

# Confirmados no TODOCTE.md via Nota Tecnica 2015/002:
URL = "https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx"
METHOD = "cteDistDFeInteresse"

# HIPOTESES ainda nao confirmadas por teste real — ajustar se a SEFAZ reclamar na resposta:
VERSION = os.environ.get("VERSION", "1.00")
NS_SCHEMA = os.environ.get("NS_SCHEMA", "http://www.portalfiscal.inf.br/cte")
NS_WSDL = os.environ.get("NS_WSDL", "http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe")

_DOC_ZIP_PATTERN = re.compile(r'<docZip NSU="(\d+)"[^>]*>(.*?)</docZip>', re.DOTALL)
_C_STAT_PATTERN = re.compile(r"<cStat>(\d+)</cStat>")
_X_MOTIVO_PATTERN = re.compile(r"<xMotivo>(.*?)</xMotivo>")
_MAX_NSU_PATTERN = re.compile(r"<maxNSU>(\d+)</maxNSU>")
_ULT_NSU_PATTERN = re.compile(r"<ultNSU>(\d+)</ultNSU>")
_CHAVE_PATTERN = re.compile(r'Id="CTe(\d{44})"')


def validate_config():
    missing = [name for name, value in [("CERT_PATH", CERT_PATH), ("CERT_PASSWORD", CERT_PASSWORD)] if not value]
    if missing:
        print(f"Faltando variavel de ambiente: {', '.join(missing)}")
        sys.exit(1)


def create_envelope(ult_nsu: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
        <soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <{METHOD} xmlns="{NS_WSDL}">
              <cteDadosMsg>
                <distDFeInt xmlns="{NS_SCHEMA}" versao="{VERSION}">
                  <tpAmb>{TP_AMB}</tpAmb>
                  <cUFAutor>{UF_AUTOR}</cUFAutor>
                  <CNPJ>{CNPJ}</CNPJ>
                  <distNSU><ultNSU>{ult_nsu}</ultNSU></distNSU>
                </distDFeInt>
              </cteDadosMsg>
            </{METHOD}>
          </soap12:Body>
        </soap12:Envelope>"""


def query(ult_nsu: str) -> str:
    envelope = create_envelope(ult_nsu)
    headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
    print(f"Consultando {URL} (ultNSU={ult_nsu}) ...")
    try:
        resp = requests_pkcs12.post(
            URL,
            data=envelope.encode("utf-8"),
            pkcs12_filename=CERT_PATH,
            pkcs12_password=CERT_PASSWORD,
            headers=headers,
            timeout=30,
        )
    except requests.exceptions.SSLError as e:
        print("Erro de SSL/TLS — cadeia de confianca do certificado do SERVIDOR, ou senha/certificado errado.")
        print(f"Detalhe: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Erro de conexao: {e}")
        sys.exit(1)

    print(f"Status HTTP: {resp.status_code}")
    return resp.text


def process_batch(raw: str):
    """Retorna (chave_encontrada: bool, ult_nsu_resp: str|None, max_nsu: str|None, tem_docs: bool)."""
    cstat = _C_STAT_PATTERN.search(raw)
    xmotivo = _X_MOTIVO_PATTERN.search(raw)
    max_nsu = _MAX_NSU_PATTERN.search(raw)
    ult_nsu_resp = _ULT_NSU_PATTERN.search(raw)

    if cstat:
        print(f"cStat: {cstat.group(1)}", end="  ")
    if xmotivo:
        print(f"xMotivo: {xmotivo.group(1)}", end="  ")
    if ult_nsu_resp:
        print(f"ultNSU: {ult_nsu_resp.group(1)}", end="  ")
    if max_nsu:
        print(f"maxNSU: {max_nsu.group(1)}")

    docs = _DOC_ZIP_PATTERN.findall(raw)
    print(f"  documentos no lote: {len(docs)}")

    found = False
    for nsu, encoded in docs:
        try:
            decoded = gzip.decompress(base64.b64decode(encoded)).decode("utf-8")
        except Exception as e:
            print(f"    NSU {nsu}: erro ao decodificar docZip: {e}")
            continue

        chave_match = _CHAVE_PATTERN.search(decoded)
        chave = chave_match.group(1) if chave_match else None

        if chave == TARGET_CHAVE:
            found = True
            print(f"    NSU {nsu}: chave {chave}  <-- CHAVE ALVO!")
            print("\n--- documento encontrado, primeiros 2000 caracteres ---")
            print(decoded[:2000])
        elif chave and chave[:20] == TARGET_CHAVE[:20]:
            # mesmo cUF+AAMM+CNPJ do alvo (mesmo emitente/periodo) — so pra acompanhar que estamos
            # avancando na direcao certa, sem poluir o log com as dezenas de outras transportadoras
            print(f"    NSU {nsu}: chave {chave}  (mesmo emitente do alvo, nNF diferente)")

    return found, (ult_nsu_resp.group(1) if ult_nsu_resp else None), (max_nsu.group(1) if max_nsu else None), bool(docs)


def main():
    validate_config()
    ult_nsu = ULT_NSU

    for lote in range(1, MAX_LOTES + 1):
        print(f"\n=== Lote {lote} (ultNSU={ult_nsu}) ===")
        raw = query(ult_nsu)
        found, ult_nsu_resp, max_nsu, tem_docs = process_batch(raw)

        if found:
            print(f"\nAchou a chave alvo em {lote} lote(s). Encerrando.")
            return

        if not tem_docs:
            print("\nLote sem documentos — provavelmente chegou ao fim do que esta disponivel (cStat 137?).")
            return

        if ult_nsu_resp is None:
            print("\nNao consegui ler o ultNSU da resposta — parando por seguranca (confere o corpo bruto acima).")
            return

        if max_nsu is not None and ult_nsu_resp >= max_nsu:
            print(f"\nChegou no maxNSU ({max_nsu}) sem achar a chave alvo. Ela pode nao estar disponivel nesse papel/CNPJ, ou o volume real e maior do que o esperado — reavaliar com o TODOCTE.md antes de seguir.")
            return

        ult_nsu = ult_nsu_resp
        time.sleep(1)  # educado com o webservice da SEFAZ, nao martela sem pausa

    print(f"\nParou em {MAX_LOTES} lotes (MAX_LOTES) sem achar a chave. Rode de novo com ULT_NSU={ult_nsu} pra continuar de onde parou, ou aumente MAX_LOTES.")


if __name__ == "__main__":
    main()
