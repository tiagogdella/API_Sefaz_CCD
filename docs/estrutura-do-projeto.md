# Estrutura do Projeto — API_Sefaz

Mapa de pastas/arquivos do serviço, pra quem está vendo uma API pela primeira vez entender o que
cada peça faz e por que existe. Reflete o estado real do projeto nesta data (30/07/2026) — conforme
crescer (Fase 2 em diante), este doc precisa ser atualizado junto.

---

## 1. Árvore de pastas e arquivos

```mermaid
flowchart TD
    Root["API_Sefaz/"]

    Root --> Env[".env\nSEUS valores reais (certificado, senha, CNPJ)\nNUNCA vai pro git"]
    Root --> EnvExample[".env.example\nmodelo sem segredo, serve de referência\neste SIM vai pro git"]
    Root --> Gitignore[".gitignore\nlista o que o git deve ignorar\n(.venv, .env, *.pfx, __pycache__)"]
    Root --> Todo["TODO.md\nplano de trabalho, fases, decisões"]
    Root --> Poc["poc_consulta.py\nscript descartável da Fase 0\n(provou que a integração funciona;\nvai ser removido quando o cliente\nreal, dentro de app/, cobrir tudo)"]
    Root --> Docs["docs/\ndocumentação (este arquivo mora aqui)"]
    Root --> App["app/\no código da aplicação em si"]
    Root --> Venv[".venv/\nambiente Python isolado\n(nunca vai pro git)"]

    Docs --> DocsArch["arquitetura-geral.md\nvisão geral dos 2 serviços do sistema"]
    Docs --> DocsProto["protocolo-sefaz.md\nregras da SEFAZ (uso indevido, manifestação...)"]
    Docs --> DocsEstrutura["estrutura-do-projeto.md\neste arquivo"]

    App --> AppInit["__init__.py\narquivo vazio — só diz ao Python\n'esta pasta é um pacote importável'"]
    App --> Main["main.py\nponto de entrada: cria o FastAPI,\nregistra os endpoints"]
    App --> Core["core/\nconfiguração central, coisas\nque o app inteiro compartilha"]
    App --> Services["services/\nlógica de negócio — não sabe\nnada sobre HTTP"]
    App --> ApiFuture["api/  (ainda não existe)\nvai ganhar vida quando tivermos\nendpoints demais pra caber\nno main.py"]
    App --> SchemasFuture["schemas/  (ainda não existe)\nvai ter os formatos Pydantic de\nrequest/response quando o endpoint\nde consulta ficar mais rico"]

    Core --> Config["config.py\nclasse Settings (Pydantic BaseSettings)\nlê e valida o .env uma vez só"]

    Services --> ServicesInit["__init__.py"]
    Services --> SefazClient["sefaz_client.py\nfala com a SEFAZ: monta o SOAP,\nenvia via mTLS, devolve o XML cru"]
```

## 2. Por que separado assim (camadas)

Mesma ideia do `controleDeCompra` (documentada em
[`controleDeCompra/docs/request-flow.md`](../../controleDeCompra/docs/request-flow.md)):
cada camada só conhece a de baixo, nunca a de cima. Isso facilita testar cada pedaço isolado e
trocar uma peça sem quebrar as outras.

```mermaid
flowchart LR
    Client(["Cliente HTTP\n(ex: backend do monolito,\nou você testando com curl)"])
    Main["main.py\nrecebe a requisição HTTP,\ndecide o que fazer com ela"]
    Schemas["Pydantic models\n(ainda a criar)\nvalida o formato do request/response\n— mesmo papel do zod no TS"]
    Services["services/sefaz_client.py\nlógica pura: monta XML,\nfala com a SEFAZ, devolve resultado.\nNÃO sabe o que é 'requisição HTTP'"]
    Core["core/config.py\nconfiguração compartilhada\n(certificado, CNPJ, ambiente)"]
    Sefaz(["SEFAZ\nwebservice externo do governo"])

    Client -->|"HTTP POST /consultas/nfe"| Main
    Main <-->|valida o corpo| Schemas
    Main --> Services
    Services --> Core
    Services <-->|"SOAP sobre mTLS"| Sefaz
    Main -->|resposta HTTP| Client
```

**Regra chave**: só o `main.py` (e futuramente `app/api/*.py`) deveria "saber" que existe uma
requisição HTTP. `services/sefaz_client.py` recebe uma chave de acesso (uma `string` comum) e
devolve um resultado — ele funcionaria igual se fosse chamado por um teste automatizado, por uma
linha de comando, ou por um endpoint. Isso é o que torna a lógica fácil de testar sem precisar
subir um servidor inteiro.

## 3. O que cada arquivo faz, em uma frase

| Arquivo/pasta | O que faz | Analogia com o `controleDeCompra` (TS) |
|---|---|---|
| `app/main.py` | Cria a aplicação FastAPI e registra os endpoints | `backend/src/index.ts` + `routes/*.routes.ts` |
| `app/core/config.py` | Lê e valida as variáveis de ambiente uma vez, no início | Não tem equivalente direto — o TS lê `process.env` espalhado com `dotenv` |
| `app/services/sefaz_client.py` | Lógica de negócio: fala com a SEFAZ | `backend/src/services/*.service.ts` |
| `app/api/` (futuro) | Quando os endpoints crescerem, saem do `main.py` e viram arquivos próprios aqui | `backend/src/routes/*.routes.ts` + `controllers/*.controller.ts` |
| `app/schemas/` (futuro) | Formatos Pydantic de entrada/saída dos endpoints | `backend/src/schemas/*.schema.ts` (zod) |
| `.env` / `.env.example` | Configuração sensível vs. modelo público | Mesmo padrão já usado no `controleDeCompra` |
| `poc_consulta.py` | Script isolado que só existiu pra provar que a integração com a SEFAZ funciona antes de construir o serviço de verdade | Não tem equivalente — foi só uma etapa de validação (Fase 0) |

## 4. Por que `api/` e `schemas/` ainda não existem

De propósito — a regra que temos seguido neste projeto é criar estrutura **quando o código que vai
morar ali já existe**, não antes. Com só 2 endpoints (`/health` e o futuro `/consultas/nfe`), tudo
cabe direto no `main.py` sem ficar confuso. Quando isso crescer (mais endpoints, schemas mais
ricos), a gente separa — daí esse doc é atualizado junto.

## 5. Referências

- [`arquitetura-geral.md`](arquitetura-geral.md) — como este serviço se encaixa com o `controleDeCompra`
- [`protocolo-sefaz.md`](protocolo-sefaz.md) — regras específicas do webservice da SEFAZ
- [`controleDeCompra/docs/request-flow.md`](../../controleDeCompra/docs/request-flow.md) — o mesmo padrão de camadas, do lado TypeScript
