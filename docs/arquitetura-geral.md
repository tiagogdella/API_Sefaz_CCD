# Arquitetura Geral — Sistema de Compras

Visão de alto nível de como o **monolito `controleDeCompra`** (TypeScript) e o **serviço `API_Sefaz`**
(Python) se encaixam, e como tudo roda em produção. Atualizado em 06/08/2026.

---

## 1. Componentes

```mermaid
flowchart TB
    subgraph Cliente
        Browser["Navegador\n(Vue 3 + Naive UI)"]
        Scanner["Leitor de código de barras/QR\n(input USB)"]
    end

    subgraph controleDeCompra["Monolito controleDeCompra (TypeScript)"]
        Frontend["frontend/\nVite + Vue 3 + Nginx"]
        Backend["backend/\nExpress + Prisma"]
        Postgres[("Postgres")]
        AI["Gemini API\n(sugestão de categoria de produto)"]
    end

    subgraph API_Sefaz["API_Sefaz (Python)"]
        FastAPI["FastAPI\nPOST /consultas/nfe\nPOST /consultas/xml"]
        SefazClient["sefaz_client\n(orquestra consulta + manifestação)"]
        Certs[("Certificados A1 (.pfx)\nmúltiplos CNPJs: della, migra")]
    end

    SEFAZ["SEFAZ — Ambiente Nacional\nNFeDistribuicaoDFe + NFeRecepcaoEvento4"]

    Scanner -->|"chave de 44 dígitos"| Browser
    Browser <-->|HTTP/JSON| Frontend
    Frontend <-->|"REST API (/api)"| Backend
    Backend <-->|Prisma| Postgres
    Backend -.->|"sugestão de categoria\n(produto novo)"| AI
    Backend -->|"POST, X-API-Key\n(rede interna k8s)"| FastAPI
    FastAPI --> SefazClient
    SefazClient -.->|carrega uma vez| Certs
    SefazClient <-->|"SOAP sobre mTLS"| SEFAZ
    FastAPI -->|"JSON tratado ou XML bruto"| Backend
```

**Por que dois serviços separados, em linguagens diferentes**: a integração com a SEFAZ depende
de SOAP + assinatura XML + certificado PKCS12, área onde o ecossistema Python (`xmlsec`,
`cryptography`) é mais maduro. Como a comunicação entre os dois é só HTTP/JSON, a escolha de
linguagem de um lado fica isolada e de baixo risco pro outro.

## 2. Produção (Kubernetes/k3s)

```mermaid
flowchart LR
    subgraph Remoto["Acesso remoto"]
        Contador(("Contador\nhome office"))
    end

    Contador -->|WireGuard VPN| LAN

    subgraph LAN["Rede local / servidor (k3s)"]
        Traefik["Traefik (Ingress)\nporta 80"]

        subgraph NS["namespace comprassularroz"]
            FrontendPod["frontend\n(Nginx)"]
            BackendPod["backend\n(Express)"]
            SefazPod["sefaz\n(FastAPI) — sem porta externa"]
            PgPod[("postgres")]
            SecretCerts[("Secret sefaz-certs\n(.pfx como arquivo)")]
            SecretConfig[("Secret sefaz-secrets\n(senhas, CNPJ, API key)")]
        end
    end

    SEFAZ_EXT["SEFAZ (internet, mTLS)"]

    Traefik --> FrontendPod
    FrontendPod -->|"/api/*"| BackendPod
    BackendPod --> PgPod
    BackendPod -->|"X-API-Key"| SefazPod
    SefazPod -.->|monta como volume| SecretCerts
    SefazPod -.->|env vars| SecretConfig
    SefazPod -->|mTLS| SEFAZ_EXT
```

Pontos importantes:
- **`sefaz` não expõe porta pra fora do cluster** — só o `backend` fala com ele, via `Service`
  `ClusterIP` (`http://sefaz:8000`), guardando um certificado com validade jurídica.
- **Certificados como Secret de arquivo**, não variável de texto — montados como volume em
  `/certs` dentro do pod (ver `k8s/deployment.yaml`).
- **Acesso remoto via VPN existente** (WireGuard, já usado pra outro sistema) — o contador
  acessa a rede local de casa, sem precisar expor o serviço na internet.

## 3. Fluxo ponta a ponta — pré-preencher formulário de compra

```mermaid
sequenceDiagram
    actor Usuário
    participant Frontend
    participant Backend as Backend (monolito)
    participant Sefaz as API_Sefaz
    participant SefazGov as SEFAZ (Ambiente Nacional)

    Usuário->>Frontend: escaneia código de barras/QR
    Frontend->>Frontend: valida formato (44 dígitos + dígito verificador módulo 11)
    Frontend->>Backend: GET /sefaz/nfe/:accessKey
    Backend->>Sefaz: POST /consultas/nfe { accessKey }
    Sefaz->>SefazGov: consChNFe (tenta cada certificado configurado)

    alt só resumo disponível
        SefazGov-->>Sefaz: resNFe (sem itens)
        Sefaz->>SefazGov: manifestação (Ciência da Operação, assinada)
        Sefaz->>SefazGov: consChNFe de novo
        SefazGov-->>Sefaz: nfeProc completo
    else já completo
        SefazGov-->>Sefaz: nfeProc completo
    end

    Sefaz-->>Backend: JSON (emitente, itens líquidos, totais)
    Backend-->>Frontend: pré-preenche formulário
    Backend-->>Backend: auto-cadastra fornecedor/produtos que não existem
    opt produto novo
        Backend->>AI: sugestão de categoria (Gemini)
    end
    Usuário->>Frontend: revisa e confirma
    Frontend->>Backend: POST /purchases
```

Detalhe de erros/regras de uso indevido está em [`protocolo-sefaz.md`](protocolo-sefaz.md).

## 4. Fluxo — "Consultar XML" (download avulso, ex: contador)

```mermaid
sequenceDiagram
    actor Contador
    participant Frontend
    participant Backend
    participant Sefaz as API_Sefaz

    Contador->>Frontend: cola a chave de acesso
    Frontend->>Backend: GET /sefaz/xml/:accessKey
    Backend->>Sefaz: POST /consultas/xml { accessKey }
    Sefaz-->>Backend: XML bruto assinado (nfeProc)
    Backend-->>Frontend: XML (Content-Disposition: attachment)
    Frontend-->>Contador: download do arquivo .xml
```

Cobre qualquer nota do CNPJ (não só as já lançadas como compra) — tenta cada certificado
configurado automaticamente, sem o usuário escolher qual.

## 5. Decisões registradas (resumo — detalhe em cada TODO)

| Decisão | Onde foi registrada |
|---|---|
| Python pro `API_Sefaz`, isolado do monolito TS | `API_Sefaz/TODO.md` |
| Certificado A1 (e-CNPJ), não A3 | `API_Sefaz/TODO.md` |
| Webservice nacional `NFeDistribuicaoDFe` em vez de raspar HTML da SEFAZ-SC | `controleDeCompra/TODO.md` (Semana 8) |
| Suporte a múltiplos CNPJs com detecção automática | `API_Sefaz/TODO.md` |
| Deploy em k3s (não docker-compose) com Secrets de arquivo pros certificados | `API_Sefaz/TODO.md`, `docs/deploy.md` (monolito) |
| Categorização de produto por IA (Gemini, tier gratuito) — sem MCP aqui, MCP é projeto separado | `controleDeCompra/TODO.md` |

## 6. Referências

- [`TODO.md`](../TODO.md) (neste repo) — plano de trabalho completo
- [`docs/protocolo-sefaz.md`](protocolo-sefaz.md) (neste repo) — protocolo SEFAZ em detalhe
- [`docs/estrutura-do-projeto.md`](estrutura-do-projeto.md) (neste repo) — mapa de pastas/arquivos
- `controleDeCompra/TODO.md` (repo separado) — plano de trabalho do monolito
- `controleDeCompra/docs/erd.md` (repo separado) — schema do banco
- `controleDeCompra/docs/request-flow.md` (repo separado) — arquitetura em camadas do backend
- `controleDeCompra/docs/deploy.md` (repo separado) — runbook de deploy no k3s

> Nota: `controleDeCompra` e `API_Sefaz` são repositórios git separados — os links pra lá acima
> são referências de caminho local, não resolvem no GitHub.