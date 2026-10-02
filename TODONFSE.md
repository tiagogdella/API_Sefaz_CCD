# TODO — Consulta de XML de NFS-e (Nota Fiscal de Serviço, padrão nacional)

Plano de implementação da consulta de NFS-e (Nota Fiscal de Serviço Eletrônica, padrão nacional)
via Ambiente de Dados Nacional (ADN), análoga à consulta de NF-e/CT-e já implementadas e em
produção. Documento vivo — marcar cada item com `[x]` conforme for concluindo, e registrar
resultado real de cada teste (não deixar como suposição), mesmo padrão do `TODOCTE.md`.

---

## Contexto

Gatilho (02/10/2026): usuário tentou consultar, via `/consultas/xml`, uma "nota de serviço" da
Della com uma chave de **50 dígitos** — o endpoint rejeitou por "não ter 44 dígitos". A validação
estava certa: não é uma chave de NF-e/CT-e digitada errada, é uma chave de **NFS-e Nacional**, que
tem formato diferente de propósito. Pesquisa confirmou: NFS-e Nacional (Lei Complementar 214/2025)
é um sistema **totalmente separado** da NF-e/CT-e, que o `API_Sefaz` hoje não sabe consultar.

**Objetivo**: dar ao `controleDeCompra` uma forma de baixar o XML de NFS-e pela chave de 50
dígitos, no mesmo espírito do `POST /consultas/xml` (NF-e) e `POST /consultas/cte/xml` (CT-e) que
já existem.

## Achados confirmados (02/10/2026 — pesquisa documental, ainda sem teste real)

> Fontes: Manual dos Contribuintes — APIs ADN Sistema Nacional NFS-e (gov.br/nfse, documentação
> técnica oficial), Swagger da produção restrita (`adn.producaorestrita.nfse.gov.br`), e relatos
> de terceiros (fórum ACBr, nfe.io) usados só pra cruzar informação — nenhuma decisão de código
> baseada só em blog de fornecedor, mesmo critério do `TODOCTE.md`.

- **Arquitetura bem diferente de NF-e/CT-e**: a distribuição de NFS-e é feita por uma **API
  REST/JSON** no Ambiente de Dados Nacional (ADN), **não SOAP**. Isso quebra a suposição que valeu
  pra CT-e ("mesmo espírito do webservice de NF-e") — aqui não tem envelope SOAP, não tem
  `distDFeInt`, não tem `cStat`/`xMotivo` (supondo; a confirmar na Fase 0).
- **URLs**: produção `https://adn.nfse.gov.br/contribuintes/...`; produção restrita (sandbox, pra
  testar sem afetar nada real) com Swagger em `https://adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html`.
  ⚠️ Relato de terceiro (fórum ACBr) menciona que o Swagger já chegou a documentar o path como
  `/contribuinte/DFe/{NSU}` (singular) quando o path real exigido era `/contribuintes/DFe/{NSU}`
  (plural) — pode já estar corrigido, mas é o tipo de detalhe que só teste real confirma, não
  copiar a doc de cabeça.
- **Endpoint com consulta direta por chave** — `GET /nfse/{chaveAcesso}`. Se confirmado, é uma
  boa notícia: diferente do CT-e (que **não tem** consulta direta por chave, só `distNSU` +
  filtro client-side, ver `TODOCTE.md`), a NFS-e parece mais parecida com a NF-e (`consChNFe`)
  nesse aspecto.
- Outros endpoints relevantes: `GET /contribuintes/DFe/{NSU}` (distribuição em lote por NSU, pro
  caso de precisar de fallback análogo ao `distNSU` do CT-e) e `GET /nfse/{chaveAcesso}/eventos`
  (eventos ligados à nota, ex: cancelamento). Existe também uma consulta que acha a chave a partir
  do identificador da DPS, mas só devolve o resultado se o certificado usado pertencer a um ator
  (prestador/tomador/intermediário) da nota — sigilo fiscal.
- **Autenticação**: mTLS com certificado ICP-Brasil A1/A3 — mesmo tipo que a Della e a Migra já
  têm cadastrado, nenhum certificado novo necessário. A documentação indica que a consulta aceita
  qualquer certificado cujo **CNPJ raiz** bata com o contribuinte consultado, sem mencionar um
  passo de credenciamento separado no portal do ADN — mas isso é suposição de doc, entra na lista
  de confirmar empiricamente (o CT-e já nos ensinou que a doc nem sempre bate com o comportamento
  real, ex: a surpresa do NSU inicial não começar em 1).
- **Payload**: JSON nas rotas, mas o documento fiscal em si deve vir como XML assinado (XMLDSIG),
  comprimido em gzip+base64 — mesmo padrão de empacotamento do `docZip` da NF-e/CT-e, só que
  dentro de um envelope JSON em vez de SOAP. Formato exato do corpo de resposta (JSON puro? XML
  direto? campo com base64?) **não confirmado**, só por teste real.
- **Chave de acesso: 50 dígitos** (não 44) — bate com o que o usuário reportou (e com o fato do
  DANFSe só ter QR code, sem código de barras, diferente do DANFE/DACTE). Composição:
  Cód.Município IBGE (7) + Ambiente de Geração (1) + Tipo de Inscrição Federal (1) + Inscrição
  Federal (14) + Nº da NFS-e (13) + AnoMês de Emissão (4) + Código Numérico (9) + Dígito
  Verificador (1) = 50. Algoritmo exato do DV **não confirmado** (supondo módulo 11 como NF-e/CT-e,
  mas não testado — ver Fase 1).

## Decisão de arquitetura (proposta, a confirmar na Fase 0/1)

**Módulo novo e separado**, `app/services/nfse_client.py` — mesmo raciocínio do `TODOCTE.md`
(abstrair 3 protocolos diferentes antes de conhecer bem o terceiro é especulativo, e não vale
arriscar o que já está em produção).

Mas aqui a diferença é **maior** do que NF-e vs CT-e: é REST/JSON, não SOAP. Então:

**Não reaproveitável** (específico de SOAP/XML dos outros dois): `parse_status`,
`extract_documents` de `sefaz_client.py`, e os equivalentes de `cte_client.py` — precisam de um
parsing JSON próprio desde o início, sem herdar nada dessas funções.

**Reaproveitável sem alteração:**
- `app/core/config.py` (`settings`, `CertificateProfile`, `get_certificate_profiles()`) — mesmos
  certificados da/migra já cadastrados, só muda o transporte (chamada REST em vez de SOAP)
- `app/services/rate_limiter.py` (`check_cooldown`/`register_not_found`) — mesma lógica de
  cooldown por `(cnpj, access_key)`; chave de 50 dígitos nunca colide com as de 44 dígitos da
  NF-e/CT-e, mesmo raciocínio já documentado no `TODOCTE.md`
- `app/core/auth.py` (`verify_api_key`) e `app/core/logging_config.py` (`log_event`) — sem mudança

## Fase 0 — Pesquisa e validação empírica (nenhum código de produção antes disso)

Script descartável `poc_consulta_nfse.py` (raiz do projeto, mesmo padrão de `poc_consulta.py` e
`poc_consulta_cte.py` — segredos só via variável de ambiente).

- [ ] Ler o Manual dos Contribuintes — APIs ADN (PDF oficial, gov.br/nfse) inteiro — a pesquisa de
      hoje foi só por busca, não leitura completa do manual
- [ ] Confirmar a URL de produção exata e o path de cada endpoint que vamos usar, testando primeiro
      no ambiente de **produção restrita** (sandbox) antes de bater em produção real — cuidado com
      a pegadinha `contribuinte`/`contribuintes` relatada por terceiro, pode já estar corrigida
- [ ] Confirmar que os certificados della/migra já cadastrados dão acesso de fato (CNPJ raiz bate
      com o papel de tomador/destinatário), sem nenhum credenciamento prévio pendente no portal
- [ ] Conseguir uma chave de 50 dígitos real pra teste — considerar reaproveitar a mesma que o
      usuário tentou em 02/10/2026 (`42046082212942976000162000000000558126108153219373`, a
      **confirmar se está correta** — ver nota abaixo) ou pedir uma nova direto do DANFSe/QR code
  - ⚠️ A chave que o usuário colou tem 50 dígitos (bate no tamanho), mas eu tentei validar módulo
    11 em alguns recortes e nenhum fechou o DV — isso pode ser normal (não confirmamos ainda o
    algoritmo real do DV da NFS-e, pode não ser módulo 11 igual NF-e/CT-e) ou pode ser erro de
    transcrição. Pedir pro usuário confirmar essa chave direto do QR code (não digitada à mão)
    antes de gastar a primeira tentativa real contra produção
- [ ] Validar localmente o formato da chave (tamanho, campos) antes de qualquer request real
- [ ] Testar `GET /nfse/{chaveAcesso}` contra produção restrita primeiro, produção depois, e
      registrar: status HTTP, formato exato do corpo de resposta, se o documento vem completo ou
      é preciso um segundo request
- [ ] Se a consulta direta por chave não funcionar (sigilo fiscal, papel não reconhecido, etc.),
      testar o fallback por NSU (`GET /contribuintes/DFe/{NSU}`) com `NSU` inicial, mesmo
      princípio do `distNSU` do CT-e
- [ ] Confirmar se existe regra de cooldown/anti-abuso documentada (igual à 1h de NF-e/CT-e) pra
      essa API, ou se o limite é outro
- [ ] Confirmar se existe algo equivalente a `cUFAutor` nessa API, ou se não se aplica (suspeita:
      não deve existir — a chave já carrega o código do município, não da UF do autor)

**Pronto quando:** teste real (produção restrita ou produção) contra uma chave conhecida devolve
o XML completo, documentado da mesma forma que `TODO.md`/`TODOCTE.md` fizeram — não só por
documentação.

---

## Fase 1 — Cliente NFS-e

A detalhar depois da Fase 0. Esboço preliminar, sujeito a mudar com o que a Fase 0 confirmar:

- [ ] `app/services/nfse_client.py`:
  - [ ] `validar_chave(access_key) -> bool` — tamanho (50) + algoritmo de DV confirmado na Fase 0
  - [ ] `get_document(access_key, profile) -> str` — chama o endpoint REST com mTLS
        (`requests_pkcs12`, igual aos outros clientes), decodifica gzip+base64 se for o caso
  - [ ] `get_document_any_cnpj(access_key) -> tuple[str, str]` — mesmo padrão de fallback entre
        `get_certificate_profiles()` dos outros dois clientes
- [ ] Decidir se existe algo análogo a `SefazError`/`SefazNotFoundError` pra reaproveitar
      (provavelmente sim, como marcadores — mas o mapeamento de "o que é erro" vem de status HTTP
      e não de `cStat`, então o `try/except` em volta da chamada REST precisa ser desenhado do
      zero, não herdado)

## Fase 2 — Endpoint e schema

- [ ] Novo `app/schemas/nfse.py` com `NFSeQueryRequest` (chave de 50 dígitos, validação de
      tamanho/DV)
- [ ] Novo endpoint `POST /consultas/nfse/xml` (espelhando `/consultas/cte/xml`)
- [ ] **Ponto de atenção pro backend/frontend do `controleDeCompra`**: hoje a tela de "consultar
      XML" provavelmente só aceita/valida 44 dígitos (foi isso que gerou o erro do usuário). Vai
      precisar diferenciar o tipo de documento pelo tamanho da chave (44 → NF-e/CT-e, 50 → NFS-e)
      **antes** de decidir pra qual endpoint do `sefaz` rotear — isso é mudança no monolito, não
      só aqui

## Fase 3 — Testes automatizados

- [ ] Mocks do cliente REST novo (sem bater na SEFAZ/ADN de verdade)
- [ ] Validador de chave de 50 dígitos (feliz/triste)
- [ ] Endpoint feliz/triste (`200`, `404`, `422`, `429`/cooldown)

## Fase 4 — Documentação

- [ ] `docs/protocolo-nfse-sefaz.md` (espelhando `docs/protocolo-cte-sefaz.md`)
- [ ] Atualizar tabela de endpoints do `README.md`
- [ ] Atualizar `docs/arquitetura-geral.md` (mais um fluxo além de NF-e/CT-e)

## Fase 5 — Deploy/config

- [ ] Confirmar se precisa de variável de ambiente nova — expectativa é que não (mesmos
      certificados della/migra, mesmos Secrets `sefaz-certs`/`sefaz-secrets`), só documentar
- [ ] Nenhuma mudança esperada em `k8s/deployment.yaml`

---

## Riscos e incertezas em aberto

1. **Maior incerteza**: não sei ainda, de fato, se `GET /nfse/{chaveAcesso}` devolve o documento
   pronto (como o `consChNFe` da NF-e) ou só um resumo/ponteiro que exige um segundo request —
   documentação de terceiro pode estar incompleta. Só teste real na Fase 0 resolve.
2. **A chave de teste que o usuário passou não validou módulo 11 em nenhum recorte** — pode ser
   só porque o DV da NFS-e usa outro algoritmo (bem possível, não é NF-e/CT-e), mas também pode
   ser erro de transcrição. Pedir confirmação via QR code antes de gastar a Fase 0 com ela.
3. Sigilo fiscal: a doc diz que a consulta por DPS só devolve a chave se o certificado pertencer a
   um ator da nota — bom sinal de que o acesso ao documento também deve respeitar isso (nosso
   caso: Della/Migra como tomadoras), mas não testado.
4. Pegadinha `contribuinte`/`contribuintes` no path, relatada por terceiro — pode já estar
   desatualizada; conferir a doc oficial atual antes de copiar qualquer URL pro código.
5. Formato de erro ainda desconhecido — API REST deve usar status HTTP padrão em vez de
   `cStat`/`xMotivo`, mas isso é suposição a confirmar, não decisão de design ainda.
6. Regra de cooldown/anti-abuso da ADN desconhecida — não presumir que é igual a 1h de NF-e/CT-e
   sem confirmar (ver Fase 0).

## Arquivos críticos

| Arquivo | Papel |
|---|---|
| `app/services/sefaz_client.py` / `cte_client.py` | Referência de padrão (fallback entre perfis, logging), **não** de parsing (SOAP/XML não se aplica aqui) |
| `app/services/nfse_client.py` (novo) | Fase 1 |
| `app/schemas/nfse.py` (novo) | Fase 2 |
| `app/main.py` | Novo endpoint `POST /consultas/nfse/xml`, sem alterar os existentes |
| `app/core/config.py` | Sem alteração esperada |
| `docs/protocolo-nfse-sefaz.md` (novo) | Modelo: `docs/protocolo-cte-sefaz.md` |
| `controleDeCompra` (monolito) | Validação de chave de acesso hoje só aceita 44 dígitos — precisa aceitar 50 e rotear pro endpoint certo |

## Verificação end-to-end

- [ ] Rodar `poc_consulta_nfse.py` contra produção restrita e depois produção, com chave real →
      documento completo
- [ ] Subir o serviço local, chamar `POST /consultas/nfse/xml` com `X-API-Key` válido e a mesma
      chave real → `200`, XML completo batendo com o teste da Fase 0
- [ ] Testar caso de erro: chave de 44 dígitos (NF-e/CT-e) no endpoint de NFS-e → `422`
- [ ] Testar a chave original que o usuário tentou em 02/10/2026 (ou uma nova, se essa não servir
      mais) ponta a ponta: frontend → backend → `sefaz` → ADN
- [ ] `python -m pytest` — todos os testes (existentes + novos) passando
