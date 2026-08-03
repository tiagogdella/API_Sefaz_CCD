from fastapi import FastAPI, HTTPException, Response
from app.core.config import settings
from app.schemas.nfe import NFeQueryRequest, NFeQueryResponse
from app.services import sefaz_client

app = FastAPI(title="API Sefaz")

@app.get("/health")
def health():
    return {"status": "ok", "cnpj": settings.cnpj}

@app.post("/consultas/nfe", response_model=NFeQueryResponse)
def query_nfe(payload: NFeQueryRequest):
    try:
        raw_response = sefaz_client.query_by_access_key(payload.access_key)
        c_stat, x_motivo = sefaz_client.parse_status(raw_response)
        documents = sefaz_client.extract_documents(raw_response)
        print(documents)
    except sefaz_client.SefazError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return NFeQueryResponse(c_stat=c_stat, x_motivo=x_motivo)

@app.post("/consultas/xml")
def query_xml(payload: NFeQueryRequest):
    try:
        xml_document = sefaz_client.get_full_document(payload.access_key)
    except sefaz_client.SefazError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return Response(content=xml_document, media_type="application/xml")