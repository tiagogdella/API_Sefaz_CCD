from lxml import etree

from app.schemas.nfe import NfeItem, NfeParsed

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
NS = {"nfe": NFE_NS}


def parse_nfe_proc(xml_document: str) -> NfeParsed:
    root = etree.fromstring(xml_document.encode("utf-8"))
    inf_nfe = root.find(".//nfe:infNFe", namespaces=NS)

    access_key = inf_nfe.get("Id").replace("NFe", "")
    issue_date = inf_nfe.findtext("nfe:ide/nfe:dhEmi", namespaces=NS)
    total_amount = inf_nfe.findtext("nfe:total/nfe:ICMSTot/nfe:vNF", namespaces=NS)

    emit = inf_nfe.find("nfe:emit", namespaces=NS)
    supplier_cnpj = emit.findtext("nfe:CNPJ", namespaces=NS)
    supplier_name = emit.findtext("nfe:xNome", namespaces=NS)

    items = []
    for det in inf_nfe.findall("nfe:det", namespaces=NS):
        prod = det.find("nfe:prod", namespaces=NS)
        items.append(
            NfeItem(
                code=prod.findtext("nfe:cProd", namespaces=NS),
                description=prod.findtext("nfe:xProd", namespaces=NS),
                quantity=float(prod.findtext("nfe:qCom", namespaces=NS)),
                unit=prod.findtext("nfe:uCom", namespaces=NS),
                unit_price=float(prod.findtext("nfe:vUnCom", namespaces=NS)),
                total_price=float(prod.findtext("nfe:vProd", namespaces=NS)),
            )
        )

    return NfeParsed(
        access_key=access_key,
        supplier_cnpj=supplier_cnpj,
        supplier_name=supplier_name,
        issue_date=issue_date,
        total_amount=float(total_amount),
        items=items,
    )
