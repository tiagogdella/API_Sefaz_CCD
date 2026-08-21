# API_Sefaz

Python/FastAPI microservice that integrates the purchase-control system with SEFAZ's national
**NFe Distribuição DFe** and **Manifestação do Destinatário** webservices, authenticated via
digital certificate (e-CNPJ, A1) over mTLS. It gives the [`controleDeCompra`](../controleDeCompra)
monolith a clean JSON/XML contract instead of dealing with SOAP, certificates and XML signing
directly.

Supports multiple CNPJ certificates (`della`, `migra`) — a lookup automatically tries each
configured certificate until it finds the document, with no manual selection required.

📄 Deeper documentation (with Mermaid diagrams): [`docs/arquitetura-geral.md`](../docs/arquitetura-geral.md)
(how this fits with the monolith), [`docs/protocolo-sefaz.md`](docs/protocolo-sefaz.md) (NF-e
protocol details, rate limits, gotchas), [`docs/protocolo-cte-sefaz.md`](docs/protocolo-cte-sefaz.md)
(CT-e protocol details — different national endpoint, no direct key lookup),
[`docs/estrutura-do-projeto.md`](docs/estrutura-do-projeto.md) (folder-by-folder map) and
[`TODO.md`](TODO.md) / [`TODOCTE.md`](TODOCTE.md) (roadmap and decision log).

## Requirements

- Python 3.10+
- System libraries for `xmlsec` (only needed to install/build locally — already handled inside the
  Docker image): `libxml2-dev`, `libxmlsec1-dev`, `libssl-dev`, `pkg-config`, a C compiler
  (`build-essential` on Debian/Ubuntu)
- A digital certificate (A1, `.pfx`/`.p12`) per CNPJ this service should be able to query

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes requirements.txt + pytest
```

Copy `.env.example` to `.env` and fill in real values (see [Environment variables](#environment-variables)).

### OpenSSL legacy provider (required for signing)

The SEFAZ manifestação event must be signed with RSA-SHA1, which OpenSSL 3 disables by default.
Point `OPENSSL_CONF` at the bundled config before running the app:

```bash
export OPENSSL_CONF=$(pwd)/openssl_legacy.cnf
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

### Test

```bash
python -m pytest
```

(use `python -m pytest`, not bare `pytest` — otherwise the `app` package won't be importable)

## Environment variables

| Variable | Description |
|---|---|
| `CERT_DELLA_PATH` | Absolute path to the "della" company's `.pfx` certificate file |
| `CERT_DELLA_PASSWORD` | Password for that certificate |
| `CERT_DELLA_CNPJ` | CNPJ (digits only) tied to that certificate |
| `CERT_DELLA_UF_AUTOR` | IBGE UF code of that company (e.g. `42` = Santa Catarina) |
| `CERT_MIGRA_PATH` / `CERT_MIGRA_PASSWORD` / `CERT_MIGRA_CNPJ` / `CERT_MIGRA_UF_AUTOR` | Same, for the "migra" company |
| `INTERNAL_API_KEY` | Shared secret required in the `X-API-Key` header on every request (except `/health`) |
| `TP_AMB` | SEFAZ environment: `1` = production, `2` = homologação |

Certificates are never committed — `.pfx`/`.p12` and `.env` are git-ignored. In production
(Kubernetes) the certificate files come from a mounted Secret volume, not a literal path on disk;
see [`k8s/deployment.yaml`](k8s/deployment.yaml).

## API

All endpoints except `/health` require the `X-API-Key` header.

| Method & path | Description |
|---|---|
| `GET /health` | Liveness/readiness check, no auth |
| `POST /consultas/nfe` | Body `{ "accessKey": "<44 digits>" }` — queries SEFAZ (trying each configured certificate), sends the manifestação event automatically if only a summary is available yet, and returns parsed JSON (supplier, items, totals) |
| `POST /consultas/xml` | Same lookup, but returns the raw signed `nfeProc` XML for download instead of parsed JSON |
| `POST /consultas/cte/xml` | Body `{ "accessKey": "<44 digits, model 57 or 67>" }` — CT-e (freight) lookup, company as tomadora. Returns the raw signed `cteProc` XML. **Different national webservice/URL than NF-e** (`www1.cte.fazenda.gov.br`, not `www1.nfe.fazenda.gov.br`) — relevant if debugging network/firewall issues in production. No structured-JSON variant yet (XML only, by design) |

All three query endpoints raise:
- `404` — key not found for any configured CNPJ
- `429` — local cooldown active (avoids triggering SEFAZ's own anti-abuse block; wait ~1h)
- `502` — connection/certificate error, or an unexpected SEFAZ rejection
- `422` — malformed access key (wrong length, non-numeric, or wrong document model for that endpoint)

## Deployment

Runs as a container in the same k3s cluster as the monolith (namespace `comprassularroz`), not
exposed outside the cluster. See manifests in [`k8s/`](k8s/) and the build/push/deploy steps in the
monolith's [`docs/deploy.md`](../controleDeCompra/docs/deploy.md).

```bash
docker build -t ghcr.io/tiagogdella/comprassularroz-sefaz:latest .
docker push ghcr.io/tiagogdella/comprassularroz-sefaz:latest
```

## Tech stack

FastAPI, Pydantic (Settings + schemas), `requests`/`requests_pkcs12` (mTLS calls), `lxml` +
`xmlsec` (building and signing the manifestação event), `cryptography` (loading the `.pfx`),
pytest.