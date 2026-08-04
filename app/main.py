from fastapi import FastAPI, HTTPException, Response
from app.core.config import settings
from app.schemas.nfe import NFeQueryRequest, NfeParsed
from app.services import sefaz_client, nfe_parser, rate_limiter

app = FastAPI(title="API Sefaz")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/consultas/xml")
def query_xml(payload: NFeQueryRequest):
    try:
        xml_document, _ = sefaz_client.get_full_document_any_cnpj(payload.access_key)
    except rate_limiter.RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except sefaz_client.SefazNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except sefaz_client.SefazError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return Response(content=xml_document, media_type="application/xml")


@app.post("/consultas/nfe", response_model=NfeParsed)
def query_nfe(payload: NFeQueryRequest):
    try:
        xml_document, profile_name = sefaz_client.get_full_document_any_cnpj(payload.access_key)
    except rate_limiter.RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except sefaz_client.SefazNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except sefaz_client.SefazError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return nfe_parser.parse_nfe_proc(xml_document, profile_name)

    
    
