from fastapi import FastAPI, HTTPException, Response, Depends
from app.core.config import settings
from app.schemas.nfe import NFeQueryRequest, NfeParsed
from app.services import sefaz_client, nfe_parser, rate_limiter
from app.core.auth import verify_api_key
from app.core.logging_config import configure_logging
from app.schemas.cte import CTeQueryRequest
from app.services import cte_client

configure_logging()

app = FastAPI(title="API Sefaz")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/consultas/xml", dependencies=[Depends(verify_api_key)])
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


@app.post("/consultas/nfe", response_model=NfeParsed, dependencies=[Depends(verify_api_key)])
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

@app.post("/consultas/cte/xml", dependencies=[Depends(verify_api_key)])
def query_cte_xml(payload: CTeQueryRequest):
    try:
        xml_document, _ = cte_client.get_full_document_any_cnpj(payload.access_key)
    except rate_limiter.RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except sefaz_client.SefazNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except sefaz_client.SefazError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return Response(content=xml_document, media_type="application/xml")

    
    
