# TODO — API_Sefaz (serviço de consulta de NF-e via certificado digital)

Serviço isolado, em **Python**, separado do monolito `controleDeCompra`. Comunicação entre os
dois é via HTTP: o monolito manda um `POST` com a chave de acesso, este serviço consulta a
SEFAZ (webservice nacional **NFe Distribuição DFe**, autenticado por mTLS com o certificado
digital e-CNPJ da empresa) e devolve um JSON já tratado, pronto pro monolito usar.

Contexto/decisão completa (por que Distribuição DFe em vez de raspar HTML da SEFAZ-SC) está
registrada no `TODO.md` do `controleDeCompra`, seção "Semana 8" e "Notas de decisão em aberto".

Certificado disponível: **A1** (arquivo `.pfx`/`.p12`), e-CNPJ da empresa.

📄 Documentação (diagramas Mermaid): [`docs/arquitetura-geral.md`](docs/arquitetura-geral.md) (visão geral dos dois serviços), [`docs/protocolo-sefaz.md`](docs/protocolo-sefaz.md) (regras da SEFAZ, ciclo de vida do documento, uso indevido) e [`docs/estrutura-do-projeto.md`](docs/estrutura-do-projeto.md) (mapa de pastas/arquivos deste serviço, bom pra quem está vendo uma API pela primeira vez).

Marque cada item com `[x]` conforme for concluindo.

---

## Fase 0 — Provar que a consulta funciona (fazer ANTES de estruturar o serviço)

> Objetivo único desta fase: eliminar o risco de "construir tudo e descobrir no fim que não
> dá pra acessar os dados que preciso". Nada aqui precisa ser bonito ou definitivo — é só um
> script descartável (`poc_consulta.py`) rodando na sua máquina/VM de dev.

- [x] Copiar o `.pfx` pra VM de dev, fora de qualquer pasta versionada pelo git (está em `~/Área de Trabalho/`, fora do repo)
- [x] Guardar a senha do certificado só em variável de ambiente local (nunca em texto no código ou em arquivo versionado)
- [x] Inspecionar o certificado com `openssl pkcs12 -info -in certificado.pfx -noout` e conferir: CNPJ do titular bate com o da empresa, validade ainda não expirou, é e-CNPJ (não e-CPF) — confirmado: e-CNPJ PJ A1, titular COMERCIO DE CEREAIS DELLA LTDA, CNPJ `82885781000103`, válido até **15/09/2026** (⚠️ vence em ~6 semanas — anotar renovação)
- [x] ~~Instalar `cryptography` e escrever uma função curta que abre o `.pfx`...~~ — caminho real usado foi mais simples: lib `requests-pkcs12` (usa o `.pfx` direto, sem precisar extrair/gravar cert+key manualmente)
- [x] ~~Testar contra o webservice de Status do Serviço...~~ — pulado; fomos direto pro teste real do `distDFeInt` (mesmo objetivo de validar o handshake mTLS, com resultado mais direto)
- [x] Pesquisar/confirmar a URL oficial do webservice nacional **NFeDistribuicaoDFe** (produção): `https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx`, confirmada empiricamente (respondeu com XML válido da SEFAZ)
- [x] Pegar a chave de acesso (44 dígitos) de notas reais recebidas — 3 chaves testadas
- [x] Montar e enviar a consulta por chave (`consChNFe`) contra produção com chaves reais
- [x] Confirmar se voltou o documento (`docZip`) e conseguir descompactar até o XML puro da nota — mTLS + schema OK, resposta bem formada da SEFAZ confirmada (`cStat`/`xMotivo` reconhecidos); ainda pendente achar uma chave com `cStat 138` (documento completo) pra validar o `docZip` em si — depende de uma nota emitida **depois** do primeiro acesso (30/07/2026)
- [x] Repetido com 3 chaves diferentes (fornecedores diferentes) — todas `cStat 137`, explicado pela regra de "primeiro acesso" (ver Notas de decisão)
- [x] **Checkpoint de decisão**: registrado abaixo em "Resultado do teste" — funcionou plenamente do ponto de vista técnico (mTLS, URL, schema); falta só validar o caminho de "documento encontrado" com uma nota nova

**Resultado do teste (preencher depois de rodar):**
- Data do teste: 30/07/2026
- Funcionou? Parcialmente — mTLS, certificado e URL de produção (`www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe`) confirmados funcionando; schema do envelope corrigido (namespace do `distDFeInt` precisa ser `http://www.portalfiscal.inf.br/nfe`, não o namespace do WSDL). Primeira chave testada voltou `cStat 137` (nenhum documento localizado) — investigando se é erro de digitação da chave, CNPJ (matriz/filial) errado, ou janela de retenção do documento.
- Observações / bloqueios encontrados: nenhum bloqueio estrutural até agora — o maior risco (não conseguir "conversar" com o serviço) está eliminado. Testadas 3 chaves reais/recentes com `consChNFe`, todas `cStat 137` (nenhum documento localizado). Teste via `distNSU` (a partir do NSU 0) confirmou `maxNSU: 6602` — o canal de distribuição TEM dados pra esse CNPJ (não é falta de habilitação).
- ⚠️ **Regra de protocolo confirmada (fonte: MOC/NT 2014.002, via busca)**: fazer uma nova consulta em **menos de 1 hora** depois de receber `cStat 137` (nenhum documento localizado) já conta como uso indevido e gera `cStat 656`, bloqueando novas consultas por 1h. Não tem relação com "pular NSU" (isso foi engano nosso na investigação, corrigido aqui). Implicação pro serviço real: implementar um intervalo mínimo de 1h entre consultas malsucedidas pro mesmo CNPJ, e tratar `cStat 656` como "aguarde e tente depois", não como erro fatal.
- ⚠️ **Hipótese parcialmente corrigida**: achávamos que só notas emitidas *depois* do primeiro acesso ficariam disponíveis (baseado no MOC). Na prática, uma das 3 chaves que antes voltou `cStat 137` (emitida antes do primeiro acesso de hoje) **passou a retornar `cStat 138` (documento localizado)** horas depois, no mesmo dia. Ou seja: parece que existe um atraso de indexação após o primeiro acesso que eventualmente libera histórico também, não só notas futuras — não confirmamos o mecanismo exato, só o resultado observado. Not a certeza documentada, é o que vimos acontecer.
- ✅ **Fase 0 concluída de fato**: testado via `POST /consultas/nfe` do próprio serviço (não mais o `poc_consulta.py`) — resposta `{"c_stat": "138", "x_motivo": "Documento localizado"}` em duas notas reais diferentes (31/07/2026).
- ✅ **`docZip` validado — e confirma o que a pesquisa já indicava**: sem manifestação, o `docZip` só traz o **Resumo da NF-e** (`resNFe`), não o documento completo. Campos que vêm no resumo: `chNFe`, `CNPJ`/`xNome` do emitente, `dhEmi`, `vNF` (valor total), `nProt`, `cSitNFe`. **Não vêm os itens da nota** (produto/quantidade/valor unitário) — isso só no `nfeProc` completo, depois da Manifestação do Destinatário (tarefa já listada na Fase 2). Sem manifestação, dá pra pré-preencher fornecedor/valor total/data, mas não a lista de produtos.
- ⚠️ **Requisito de escopo novo, descoberto na pesquisa**: antes de enviar o evento de **Manifestação do Destinatário** ("Ciência da Operação", "Confirmação da Operação" ou "Operação não Realizada"), só fica disponível o **Resumo da NF-e** (dados básicos) — o XML completo com itens só libera depois da manifestação. Isso significa que o `API_Sefaz` provavelmente vai precisar **enviar esse evento de manifestação**, não só consultar — adicionar isso como tarefa na Fase 2/3 antes de fechar o design da API.

---

## Fase 1 — Estrutura do projeto Python

> Só começar depois da Fase 0 dar sinal verde.

- [x] Escolher gerenciador de ambiente/pacotes — decidido na prática: `venv` + `pip` (já em uso desde a Fase 0)
- [x] Framework web: **FastAPI** ✅ confirmado em 30/07/2026 — Pydantic emparelha com o padrão `zod` já usado no backend TS, e a doc automática em `/docs` ajuda a testar o endpoint manualmente
- [x] Estrutura de pastas inicial — só `app/` criado por enquanto; subpastas (`api/`, `services/`, `schemas/`, `core/`) entram conforme o código for existindo, sem antecipar pasta vazia
- [x] `.env.example` (modelo) + `.env` real + `app/core/config.py` (Pydantic Settings) — confirmado carregando certo via `GET /health`
- [x] `.gitignore` (venv, `__pycache__`, `.env`, `*.pfx`/`*.p12`) — já commitado
- [x] `GET /health` simples pra validar que o serviço sobe — confirmado funcionando

## Fase 2 — Cliente SEFAZ (core da integração)

- [x] Módulo de certificado: `app/services/certificate.py` — carrega o `.pfx` e converte pra PEM em memória (usado por `requests_pkcs12` na consulta e por `xmlsec` na assinatura da manifestação)
- [x] Cliente SOAP: envelope manual com `requests`/`requests_pkcs12` (não usamos `zeep` — o envelope da consulta é simples o suficiente pra montar na mão, sem depender de parsing de WSDL)
- [x] Função `query_by_access_key` (`app/services/sefaz_client.py`) — monta o `consChNFe`, envia e recebe a resposta
- [x] Descompactar `docZip` — feito (`extract_documents`, base64 + gzip). **Ainda falta**: parsear o XML do `nfeProc` pra extrair estruturado (emitente, itens, valor total) — ver Fase 3, é o que falta pro `/consultas/nfe` virar "JSON tratado" de verdade
- [x] Tratar os casos de retorno sem sucesso da própria SEFAZ — `SefazNotFoundError`/`SefazError`, `cStat` mapeado (137/640/217 = não encontrado, resto = erro)
- [x] Implementar o envio do evento de **Manifestação do Destinatário** (`envEvento`/`RecepcaoEvento`, tipo "Ciência da Operação") — feito e validado com nota real em 03/08/2026: `cStat 135` (evento registrado) e a consulta seguinte já veio com `nfeProc` completo (5 itens, valores, impostos). Liberação foi **imediata**, sem espera. Detalhes técnicos (assinatura XML, `cOrgao=91` fixo, estrutura de resposta em duas camadas) em `docs/protocolo-sefaz.md`
- [x] Respeitar o intervalo mínimo de 1h entre novas consultas depois de "não encontrado" — implementado (`app/services/rate_limiter.py`): trava local em memória por `(cnpj, chave)`, bloqueia sem nem chamar a SEFAZ, devolve `429` (não erro fatal). Descobrimos no caminho mais dois códigos de "não encontrado" além do `137`/`640` (ver `docs/protocolo-sefaz.md`) — o cooldown agora registra pra qualquer resposta que não seja sucesso, não só os códigos catalogados, por segurança

## Fase 3 — Contrato da API (o que o monolito consome)

- [x] Definir o schema Pydantic da resposta — `NfeParsed`/`NfeItem` (`app/schemas/nfe.py`): fornecedor, CNPJ, data de emissão, valor total, lista de itens (código, descrição, quantidade, unidade, valor unitário, valor total)
- [x] `POST /consultas/nfe` — recebe `{ accessKey: string }`, devolve o JSON tratado com itens — testado com nota real, veio limpo e completo (03/08/2026)
- [x] Tratamento de erros HTTP consistente — `404` (não encontrado), `429` (aguarde/uso indevido), `502` (erro genérico SEFAZ/certificado), `422` (chave malformada, automático do Pydantic)
- [x] Testes automatizados dos parsers — `tests/test_nfe_parser.py`, XML de exemplo salvo em `tests/fixtures/`
- [x] **`POST /consultas/xml`** (necessidade nova, 03/08/2026) — feito e testado: consulta + manifestação automática (função `get_full_document` em `sefaz_client.py`, reaproveitável pro `/consultas/nfe` também), devolve o **XML completo cru** (`nfeProc`) via `Response(media_type="application/xml")`. Base da aba "Consultar XML" do monolito pronta do lado da API

## Fase 4 — Integração com o monolito

- [x] Serviço rodando em produção no k3s (namespace `comprassularroz`), sem porta exposta pra fora — manifests versionados em `API_Sefaz/k8s/`. Certificados via Secret de arquivo (`sefaz-certs`), senhas/CNPJ/API key via Secret de texto (`sefaz-secrets`). Testado ponta a ponta (05/08/2026): frontend → backend → `sefaz` → SEFAZ real
- [x] Autenticação entre serviços — API key simples (`X-API-Key`), testada e funcionando (`app/core/auth.py`)
- [ ] No backend do monolito, criar o client HTTP que chama `POST /consultas/nfe` do `API_Sefaz` e mapeia a resposta pro fluxo de pré-preenchimento do formulário (reaproveitando o padrão de `supplierPicker.create`/`productPicker.create` já usado no lançamento manual)
- [ ] Teste ponta a ponta: escanear/informar uma chave real no frontend → monolito chama `API_Sefaz` → formulário pré-preenchido

## Fase 5 — Polish

- [ ] Logs estruturados (sem logar a senha do certificado ou o conteúdo sensível da nota em texto puro)
- [x] `Dockerfile` de produção — `python:3.10-slim`, multi-stage, com `libxmlsec1-openssl` e o `openssl_legacy.cnf` embutido (SHA1 legado). Testado local com `docker run`, funcionando ponta a ponta (inclusive assinatura da manifestação)
- [ ] README do serviço: como rodar local, como configurar o certificado, variáveis de ambiente

---

## Notas de decisão

- **Múltiplos certificados/CNPJs**: ✅ implementado em 03/08/2026 — a empresa (contador) pode ter notas de 2 CNPJs diferentes (`della`/`migra`), então o serviço tenta cada certificado configurado (`get_certificate_profiles`) até achar a nota, sem escolha manual. Descoberta no caminho: `cStat 640` ("sem permissão pra consultar") também significa "não é desse CNPJ" na consulta — tratado igual ao `137` pra passar pro próximo certificado.
  - ✅ Testado: caminho "achou de primeira" (nota da Della).
  - ⚠️ Pendente: caminho de fallback ainda não confirmado de ponta a ponta — testamos com uma nota real da Migra e voltou "não encontrado" nos dois certificados. Foi a primeira consulta do certificado da Migra, então é bem provável ser o mesmo efeito de "primeiro acesso" da Fase 0 (nota fica disponível depois de um tempo). Assumimos que sim e seguimos — **retestar essa mesma chave (`42260845731998000132550010000016201009028410`) depois de ~1 dia**, respeitando o intervalo de 1h entre tentativas pra não contar como uso indevido.
- **Idioma do código**: ✅ confirmado em 30/07/2026 — código, comentários, nomes de função/variável e mensagens de erro internas em **inglês** (mesma convenção do `controleDeCompra`); só o frontend (texto visível pro usuário) fica em português. Conversa entre nós continua em português.
- **Linguagem**: ✅ decidido em 29/07/2026 — **Python**, isolado do monolito TypeScript. Vale a pena porque a integração depende de SOAP + assinatura XML + certificado PKCS12, área onde o ecossistema Python (`zeep`, `signxml`, `cryptography`, projetos de referência como `nfelib`) é bem mais maduro que o equivalente em Node. Comunicação entre os dois serviços é só HTTP/JSON, então a escolha de linguagem fica isolada e de baixo risco.
- **Framework web**: sugestão **FastAPI** (ainda não confirmado com o usuário — trocar por Flask se preferir algo mais simples, não muda o resto do plano).
- **Ambiente de teste**: consulta real só funciona em **produção** — homologação da SEFAZ não tem notas reais emitidas contra o CNPJ da empresa.
