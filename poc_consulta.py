import os 
import sys 
import re
import requests
import requests_pkcs12

CERT_PATH = os.environ.get("CERT_PATH")
CERT_PASSWORD = os.environ.get("CERT_PASSWORD")
ACCESS_KEY = os.environ.get("ACCESS_KEY")
CNPJ = os.environ.get("CNPJ", "82885781000103")
UF_AUTOR = os.environ.get("UF_AUTOR", "42") # 42 = SC (SAME UF FROM CERTIFICATED)
TP_AMB = os.environ.get("TP_AMB", "1") # 1 = PRODUCTION, 2 = HOMOLOG
QUERY_MODE = os.environ.get("QUERY_MODE", "chave") 
ULT_NSU = os.environ.get("ULT_NSU", "000000000000000")


URL = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
VERSION = "1.01" # VERSION FROM SCHEMA OF DISTDFEINT

def validate_config():
    required = [("CERT_PATH", CERT_PATH), ("CERT_PASSWORD", CERT_PASSWORD)]
    if QUERY_MODE == "chave":
        required.append(("ACCESS_KEY", ACCESS_KEY))
    missing = [name for name, value in required if not value]

    if missing:
        print(f"Missing enviroment variable: {', '.join(missing)}")
        sys.exit(1)
    if QUERY_MODE == "chave" and not (ACCESS_KEY.isdigit() and len(ACCESS_KEY) == 44):
        print(f"ACCESS_KEY NEEDS TO HAVE 44 CARAC. (RECIEVED {len(ACCESS_KEY)} CARAC.)")
        sys.exit(1)

def create_envelope():
    if  QUERY_MODE == "nsu":
        search = f"<distNSU><ultNSU>{ULT_NSU}</ultNSU></distNSU>"
    else: 
        search = f"<consChNFe><chNFe>{ACCESS_KEY}</chNFe></consChNFe>"   


    return f"""<?xml version="1.0" encoding="UTF-8"?>
        <soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
          <soap12:Body>
            <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
              <nfeDadosMsg>
                <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="{VERSION}">
                  <tpAmb>{TP_AMB}</tpAmb>
                  <cUFAutor>{UF_AUTOR}</cUFAutor>
                  <CNPJ>{CNPJ}</CNPJ>
                  {search}
                </distDFeInt>
              </nfeDadosMsg>
            </nfeDistDFeInteresse>
          </soap12:Body>
        </soap12:Envelope>"""

def main():
    validate_config()
    envelope = create_envelope()
    headers = {"Content-Type": "application/soap+xml; charset=utf-8"}

    print(f"Consultando {URL} ...")
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
        print("Erro de SSL/TLS — pode ser cadeia de confiança do certificado do SERVIDOR da SEFAZ")
        print("(comum em integrações com .gov.br), ou senha/certificado errado.")
        print(f"Detalhe: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Erro de conexão: {e}")
        sys.exit(1)

    print(f"Status HTTP: {resp.status_code}")
    print("--- corpo da resposta (primeiros 3000 caracteres) ---")
    print(resp.text[:3000])

    cstat = re.search(r"<cStat>(\d+)</cStat>", resp.text)
    xmotivo = re.search(r"<xMotivo>(.*?)</xMotivo>", resp.text)
    if cstat:
        print(f"\ncStat: {cstat.group(1)}")
    if xmotivo:
        print(f"xMotivo: {xmotivo.group(1)}")


if __name__ == "__main__":
    main()