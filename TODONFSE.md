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
- **⚠️ Correção pós-teste real (02/10/2026): não existe consulta direta por chave pro documento.**
  O Swagger oficial (baixado autenticado da sandbox, `/contribuintes/swagger/v1/swagger.json`)
  só lista dois métodos: `GET /DFe/{NSU}` (distribuição em lote por NSU) e
  `GET /NFSe/{ChaveAcesso}/Eventos` (só eventos, não o documento principal). **É igual ao CT-e**:
  paginar por NSU e filtrar client-side pela `ChaveAcesso` — só que aqui a chave já vem como campo
  próprio em cada item do lote (`ChaveAcesso`), sem precisar decodificar o XML antes de comparar,
  o que é mais simples que o CT-e (lá só tinha o atributo `Id="CTe"+chave` dentro do XML).
- **URLs confirmadas**: produção restrita (sandbox) `https://adn.producaorestrita.nfse.gov.br/contribuintes`,
  produção real `https://adn.nfse.gov.br/contribuintes` (plural "contribuintes" confirmado nos
  dois, sem a pegadinha que terceiros relataram).
- **Autenticação confirmada por teste real**: mTLS com o certificado della (mesmo `.pfx` já em
  uso) funcionou de primeira, sem nenhum passo de credenciamento prévio no portal do ADN. O
  certificado da migra (vencido) deu o mesmo erro de certificado expirado que já víamos no CT-e —
  confirma que o problema da migra afeta **todos** os três tipos de documento, não só CT-e.
- **Resposta é JSON** (schema `LoteDistribuicaoNSUResponse`): `StatusProcessamento` (enum
  `REJEICAO`/`NENHUM_DOCUMENTO_LOCALIZADO`/`DOCUMENTOS_LOCALIZADOS`, análogo ao `cStat` 137/138),
  `LoteDFe` (array de `{NSU, ChaveAcesso, TipoDocumento, TipoEvento, ArquivoXml, DataHoraGeracao}`),
  `Erros`/`Alertas` (array de `{Codigo, Descricao, ...}`), `TipoAmbiente` (útil pra confirmar que
  não caímos em homologação por engano). **Erro "não encontrado" vem como HTTP 404** (confirmado:
  `E2220` "Nenhum documento localizado..."), diferente de NF-e/CT-e que sempre respondem `200` e
  colocam o status dentro do XML (`cStat`) — precisa checar o status HTTP, não só o corpo.
- **Paginação confirmada por teste real**: `GET /DFe/{N}` devolve até 50 itens com `NSU > N`
  (não inclui o próprio N) — ou seja, pra continuar é só chamar de novo com `N = maior NSU do
  lote anterior`, sem reenviar o mesmo item. Achamos a chave real do usuário em **3 lotes** (NSU
  1→131), nada do susto de "janela de retenção" que tivemos no CT-e (lá começava no meio do
  histórico, não do NSU 1).
- **Documento decodificado com sucesso**: `ArquivoXml` é gzip+base64 (confirmado, mesmo padrão do
  `docZip`), decodifica pra um XML `<NFSe versao="1.01">` completo e legível (10.817 caracteres),
  com `cStat 100` (autorizado) **dentro do XML também** — mesma convenção de código da NF-e/CT-e.
  Atributo `Id="NFS" + 50 dígitos` no elemento `infNFSe` — mesmo padrão `Id="NFe"+chave`/
  `Id="CTe"+chave` já usado pelos outros dois clientes.
- **A chave que o usuário tentou em 02/10 é 100% real e válida** — achada de verdade na produção:
  nota 5581, prestador ALPHA CLEAN SERVIÇOS DE CONTROLE DE PRAGAS LTDA (CNPJ 12942976000162,
  Criciúma-SC, código IBGE 4204608 — bate com a pergunta original do usuário sobre Criciúma),
  tomador della (Meleiro-SC), serviço de dedetização, R$ 1.159,99, emitida 01/10/2026. A validação
  local de módulo 11 que eu tentei antes **falhou porque não é esse o algoritmo do DV da NFS-e**
  (confirmado agora: a chave estava certa o tempo todo) — algoritmo real do DV ainda não
  confirmado, não bloqueia o cliente (Fase 1 não depende de validar o DV, só do tamanho).
- **Chave de acesso: 50 dígitos**, composição confirmada batendo com a chave real decodificada:
  Cód.Município IBGE (7) + Ambiente de Geração (1) + Tipo de Inscrição Federal (1) + Inscrição
  Federal (14) + Nº da NFS-e (13) + AnoMês de Emissão (4) + Código Numérico (9) + Dígito
  Verificador (1) = 50.

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

- [x] Ler a documentação oficial do ADN — **manual PDF oficial é curto (3 páginas, v1.0,
      12/02/2026)**: só descreve `GET /DFe/{NSU}` e `GET /NFSe/{ChaveAcesso}/Eventos` em alto
      nível. Detalhe de schema/parâmetros veio do **Swagger real**, baixado autenticado da
      sandbox (`GET /contribuintes/swagger/v1/swagger.json` com o certificado della) — ver
      "Achados confirmados" acima
- [x] Confirmar URL/paths — **confirmado**: sandbox `adn.producaorestrita.nfse.gov.br/contribuintes`,
      produção `adn.nfse.gov.br/contribuintes`, plural nos dois, sem pegadinha
- [x] Confirmar que os certificados já cadastrados dão acesso — **della confirmado** (200 OK,
      documentos reais devolvidos). **Migra não testável** — mesmo erro de certificado expirado
      do CT-e (`Client certificate expired: Not After: 2026-09-22`), reforça que a renovação da
      migra é bloqueante pra qualquer um dos três tipos de documento, não só CT-e
- [x] Chave de teste — a do usuário (`42046082212942976000162000000000558126108153219373`) **era
      válida desde o início**; a falha do módulo 11 era só porque esse não é o algoritmo do DV da
      NFS-e (ainda não identificado, não bloqueia)
- [x] Testado contra produção restrita primeiro (`GET /DFe/0`, `GET /DFe/1`, ambos
      `NENHUM_DOCUMENTO_LOCALIZADO`/404 — esperado, sandbox não tem os documentos reais da
      della/migra) e depois produção real
- [x] **Teste real contra produção (02/10/2026)**: `GET /DFe/0` com certificado della →
      `200`/`DOCUMENTOS_LOCALIZADOS`, primeiro item já no NSU 1 (sem o susto de janela de retenção
      do CT-e). Paginando (`NSU = maior NSU do lote anterior`) achamos a chave do usuário no
      **3º lote** (NSU 131, de 1 a 131 — bem mais rápido que os ~9 lotes do CT-e). XML decodificado
      (gzip+base64) veio completo, 10.817 caracteres, `cStat 100`, documento `<NFSe versao="1.01">`
      bem formado
- [x] Sem consulta direta por chave (confirmado pelo Swagger) → fallback por NSU **é** o único
      caminho, não é fallback — é o desenho principal, igual ao CT-e
- [ ] Regra de cooldown/anti-abuso da ADN — **não documentada em lugar nenhum que achei** (nem no
      manual de 3 páginas, nem no Swagger). Decisão: aplicar o mesmo cooldown de 1h do
      `rate_limiter.py` por precaução (custo de manter é zero, mesmo raciocínio do CT-e), sem
      confirmação oficial
- [x] Equivalente a `cUFAutor` — **não existe nessa API**, nenhum parâmetro parecido no Swagger. A
      chave já carrega o município (`cLocIncid`), não precisa de UF do autor

**✅ Fase 0 concluída em 02/10/2026.** Teste real contra produção confirmou URL, autenticação,
paginação e decodificação do documento com a chave real do usuário.

---

## Fase 1 — Cliente NFS-e

- [x] `app/services/nfse_client.py`:
  - [x] `get_full_document(access_key, profile) -> str` — pagina `GET /DFe/{NSU}` (sem schema de
        envelope, diferente dos outros dois — é JSON puro), filtra por `ChaveAcesso` (campo
        próprio, sem precisar decodificar o XML antes de comparar — mais simples que o CT-e)
  - [x] `get_full_document_any_cnpj(access_key) -> tuple[str, str]` — mesmo padrão de fallback,
        **com uma melhoria**: também pula pro próximo perfil em `SefazError` genérico (não só
        `NotFound`/cooldown), pra um certificado vencido (caso real da migra) não bloquear a
        tentativa com outro certificado válido. Se nenhum perfil funcionar, propaga o último
        `SefazError` real (não disfarça de 404)
  - [x] `_decode_arquivo_xml`/`_find_in_lote` — funções puras extraídas pra dar pra testar sem
        mock de rede (mesma filosofia dos outros clientes: nenhum teste automatizado bate na rede)
- [x] Não existe `SefazError`/`SefazNotFoundError` próprio — reaproveitados de `sefaz_client.py`
      por import direto (igual ao `cte_client.py`), só o `try/except` em volta do `requests_pkcs12`
      é novo (checa `StatusProcessamento`/HTTP status, não `cStat`)

**✅ Fase 1 concluída em 02/10/2026.** Testado via REPL contra produção real (certificado della,
copiado pro pod rodando pra validar sem precisar de ambiente local completo):
`get_full_document_any_cnpj("42046082212942976000162000000000558126108153219373")` → achou via
`della`, XML completo (10.817 caracteres) idêntico ao da Fase 0.

## Fase 2 — Endpoint e schema

- [x] `app/schemas/nfse.py` com `NFSeQueryRequest` — valida 50 dígitos numéricos. **Sem validação
      de DV** (algoritmo ainda não identificado, ver Riscos) — só tamanho, mesmo nível de rigor
      que os outros schemas tinham antes de validar o modelo
- [x] Novo endpoint `POST /consultas/nfse/xml` em `app/main.py`, mesmo padrão de erro dos outros
      dois (`404`/`429`/`502`/`422`)
- [ ] **Pendente, fora do `API_Sefaz`**: o `controleDeCompra` precisa aceitar/rotear chave de 50
      dígitos (hoje só valida 44) pro endpoint novo — não foi feito, é mudança em outro repo

**✅ Fase 2 concluída em 02/10/2026** (lado do `API_Sefaz`). Testado via `requests` contra uma
instância de teste (porta 8001, separada da produção real na 8000) dentro do próprio pod:
`POST /consultas/nfse/xml` com a chave real → `200`, XML completo; chave de 44 dígitos → `422`
com mensagem clara; sem `X-API-Key` → `422` (FastAPI valida o header antes da nossa lógica).
`/health` e `/consultas/cte/xml` continuam respondendo normal — sem regressão.

## Fase 3 — Testes automatizados

- [x] `tests/test_nfse_schema.py` (4 testes) + `tests/test_nfse_client.py` (4 testes) — sem mock
      de rede, mesma filosofia dos testes de CT-e (só funções puras + fixtures/dados inline)
- [x] `python -m pytest` completo (NF-e + CT-e + NFS-e) — **21 testes passando** (13 que já
      existiam + 8 novos), rodado dentro do pod (pytest não vem na imagem de produção, instalado
      ali só pra validar, não fica no `requirements.txt`)

## Fase 4 — Documentação

- [ ] `docs/protocolo-nfse-sefaz.md` (espelhando `docs/protocolo-cte-sefaz.md`)
- [ ] Atualizar tabela de endpoints do `README.md`
- [ ] Atualizar `docs/arquitetura-geral.md` (mais um fluxo além de NF-e/CT-e)

## Fase 5 — Deploy/config

- [ ] Confirmar se precisa de variável de ambiente nova — expectativa é que não (mesmos
      certificados della/migra, mesmos Secrets `sefaz-certs`/`sefaz-secrets`), só documentar
- [ ] Nenhuma mudança esperada em `k8s/deployment.yaml`

---

## Riscos e incertezas em aberto (atualizado 02/10/2026)

**Resolvidos por teste real (02/10/2026):**
1. ~~Se existe consulta direta por chave~~ — **não existe** (confirmado pelo Swagger oficial),
   só `GET /DFe/{NSU}` + filtro client-side, igual ao CT-e
2. ~~Chave do usuário suspeita (módulo 11 não fechou)~~ — **era válida o tempo todo**; achada de
   verdade na produção (NSU 131, documento completo). O módulo 11 só não é o algoritmo certo do
   DV da NFS-e
3. ~~Pegadinha `contribuinte`/`contribuintes`~~ — confirmado `contribuintes` (plural) nos dois
   ambientes, sem problema
4. ~~Formato de erro~~ — confirmado: HTTP 404 pra "não encontrado" (`StatusProcessamento`
   `NENHUM_DOCUMENTO_LOCALIZADO`, código `E2220`), HTTP 200 + `DOCUMENTOS_LOCALIZADOS` pra sucesso
5. ~~Certificados della/migra já dão acesso~~ — della confirmado (200 real); migra não testável
   por estar vencido (mesmo problema do CT-e, não é específico da NFS-e)

**Ainda em aberto:**
1. **Algoritmo do dígito verificador da chave de 50 dígitos** — ainda não identificado. Não
   bloqueia o cliente (que só filtra por igualdade de string, não recalcula DV), mas falta pro
   schema poder rejeitar uma chave com dígitos trocados antes de gastar uma consulta real
2. **Regra de cooldown/anti-abuso da ADN** — não documentada em lugar nenhum encontrado (nem
   manual, nem Swagger). Aplicamos o cooldown de 1h do `rate_limiter.py` por precaução, sem
   confirmação oficial de que é essa a regra real (pode ser mais permissivo ou mais restritivo)
3. Sigilo fiscal na consulta por DPS (não usada aqui, só documentada) — não testado, não bloqueia
4. **Volume de paginação pode crescer** — hoje são só 131 NSUs pra della, mas isso cresce com o
   tempo/volume de notas. Sem estratégia de persistência de NSU por enquanto (mesma decisão do
   CT-e, revisar se `MAX_NSU_BATCHES=100` deixar de ser suficiente)
5. **Pendente fora do `API_Sefaz`**: mudança no `controleDeCompra` pra aceitar/rotear chave de 50
   dígitos — sem isso, o usuário continua caindo no erro de "44 dígitos" na tela, mesmo com o
   backend do `sefaz` já funcionando
6. **Deploy real bloqueado**: o `ghcr-secret` do cluster continua com o PAT expirado (mesmo
   problema de 09/09/2026, nunca resolvido) e o `imagePullPolicy` está em `IfNotPresent` — rebuild
   + push de uma imagem nova **não vai ser puxado pelo cluster** até isso ser corrigido. O código
   foi validado copiando os arquivos direto pro pod rodando (mudança efêmera, perdida no próximo
   restart) — não é um deploy real

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

- [x] Testado contra produção restrita (sandbox) e produção real, com a chave real do usuário →
      documento completo (NSU 131, 3 lotes)
- [x] `POST /consultas/nfse/xml` com `X-API-Key` válido e a mesma chave real → `200`, XML completo
- [x] Caso de erro: chave de 44 dígitos no endpoint de NFS-e → `422` com mensagem clara
- [x] Caso de erro: sem `X-API-Key` → `422` (validação do header, antes da nossa lógica)
- [x] `/health` e `/consultas/cte/xml` continuam respondendo normal (sem regressão)
- [x] `python -m pytest` — **21 testes passando** (13 existentes + 8 novos)
- [ ] **Não testado**: ponta a ponta de verdade (frontend → backend do `controleDeCompra` →
      `sefaz` → ADN) — depende da mudança pendente no monolito (ver Riscos) e do deploy real
      (bloqueado pelo `ghcr-secret`, ver Riscos)
- [ ] Teste de repetição antes de 1h (cooldown) e de chave inexistente → `429`/`404` — reaproveitam
      código já validado (`rate_limiter.py`, `SefazNotFoundError`), mas não testados de fato pra
      NFS-e especificamente (mesma ressalva que o `TODOCTE.md` registrou pro CT-e)
