# TODO — Consulta de XML de CT-e (empresa como tomadora do frete)

Plano de implementação da consulta de CT-e (Conhecimento de Transporte Eletrônico) via SEFAZ,
análoga à consulta de NF-e já implementada e em produção. Documento vivo — marcar cada item com
`[x]` conforme for concluindo, e registrar resultado real de cada teste (não deixar como suposição).

---

## Contexto

O contador pediu uma forma de baixar o XML de CT-e das notas de frete em que nossa empresa é a
**tomadora** do serviço de transporte — diferente do fluxo atual do `API_Sefaz`, que só consulta
NF-e em que somos **destinatários** das mercadorias.

**Resposta à pergunta original ("a SEFAZ tem uma comunicação pra isso?"): sim, mas com uma
diferença estrutural importante em relação à NF-e — ver "Achados confirmados" logo abaixo.** A
SEFAZ mantém, pro CT-e, um webservice nacional de Distribuição DFe (`CTeDistribuicaoDFe`) análogo
em espírito ao que já usamos pra NF-e (`NFeDistribuicaoDFe`) — mesmo público de "interessados"
(emitente, remetente, expedidor, recebedor, destinatário, tomador), mesmo Ambiente Nacional. **Mas
não é possível pedir um documento específico por chave de acesso diretamente**, como fazemos hoje
com `consChNFe` — ver detalhe abaixo.

Por isso o plano começa com uma fase de validação empírica, replicando a "Fase 0" que já foi feita
pra NF-e antes de qualquer código de produção. Parte dessa validação (pesquisa documental) já foi
feita — falta o teste real contra produção.

**Escopo combinado com o usuário**: por enquanto, só XML cru (sem parser estruturado/JSON) — um
endpoint que devolve o `cteProc` (ou equivalente confirmado na Fase 0), análogo ao
`POST /consultas/xml` que já existe pra NF-e.

## Achados confirmados (18/08/2026 — pesquisa documental, ainda sem teste real)

> Fontes primárias usadas (não blog de fornecedor, exceto onde indicado): Nota Técnica 2015/002
> ("Web Service de Distribuição de DF-e de Interesse dos Atores do CT-e, CT-e OS e GTV-e",
> [cte.fazenda.gov.br](https://www.cte.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=5c1PwLTdrCA%3D)),
> Portal do CT-e — [Web Services](https://www.cte.fazenda.gov.br/portal/webServices.aspx).

- **URL de produção confirmada**: `https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx`
  (versão 1.00) — Ambiente Nacional (não SVRS como a hipótese original supunha; a hipótese SVRS
  estava **errada**, descartada). Só o desenho da URL foi confirmado por essa página; o WSDL em si
  não pôde ser lido sem certificado (403, mesmo comportamento que já víamos com o WSDL da NF-e).
- **Método SOAP**: `cteDistDFeInteresse` (citado explicitamente na Nota Técnica), análogo ao
  `nfeDistDFeInteresse` da NF-e.
- **⚠️ Não existe consulta direta por chave de acesso.** O schema `distDFeInt` do CT-e só suporta
  dois modos, escolhidos pela tag informada no XML:
  - `distNSU` — lote de até 50 documentos a partir de um `ultNSU` informado, em ordem crescente
  - `consNSU` — um documento específico, mas por **NSU** (número sequencial gerado pelo Ambiente
    Nacional), não por chave de acesso
  - Não existe um `consChCTe` equivalente ao `consChNFe` da NF-e. Confirmado tanto pela leitura
    completa da Nota Técnica (12 páginas, nenhuma menção a consulta por chave) quanto por pesquisa
    adicional deliberada em cima disso (ver "Verificação adicional" abaixo) — não é lacuna de
    pesquisa, é como o serviço realmente funciona.
  - **Consequência pro design**: pra achar um CT-e específico (a chave escaneada pelo usuário),
    é preciso percorrer `distNSU` a partir de `ultNSU="0"` (ou de um NSU salvo de execução
    anterior) em lotes de até 50, decodificar cada `docZip`, e comparar a `chCTe` de cada
    documento com a chave procurada — filtragem client-side, não uma consulta pontual. Ver
    Fase 1 revisada abaixo.
- **Verificação adicional (insistência do usuário em 18/08)**: pesquisei especificamente se algum
  provedor comercial oferece consulta direta por chave, pra não descartar isso por pesquisa rasa.
  Achei dois casos, nenhum contradiz a conclusão acima:
  1. O portal `www.cte.fazenda.gov.br` tem uma opção "Consultar CT-e" que aceita a chave
     diretamente — mas é um **fluxo manual de navegador com CAPTCHA** (não é o webservice SOAP,
     não é automatizável), o mesmo tipo de mecanismo que o projeto decidiu evitar pra NF-e em
     29/07/2026 (troca da consulta pública SEFAZ-SC pelo webservice oficial, justamente por causa
     de CAPTCHA/instabilidade).
  2. Provedores pagos (ex: Fiscal.io Monitor) que anunciam "busca por chave" confirmam, na própria
     documentação, que por trás fazem consulta em lote (`"todos os XMLs... dos últimos 90 dias"`)
     e guardam num banco próprio — ou seja, fazem exatamente a estratégia de `distNSU` + filtro
     client-side descrita acima, só que já produtizada.
- **Cooldown de 1h confirmado oficialmente pro CT-e** (não só por analogia): a Nota Técnica diz
  textualmente que a empresa deve aguardar no mínimo uma hora pra nova solicitação quando não há
  mais documentos — mesma regra que já implementamos em `rate_limiter.py`.
- **`cStat` 137 ("Nenhum documento localizado") e 138 ("Documento localizado")** — mesmos códigos
  da NF-e, confirmado.
- **Erro 656 ("Consumo Indevido")** — mesmo mecanismo anti-abuso da NF-e, confirmado.
- **Nenhuma menção a manifestação do tomador** em toda a Nota Técnica (12 páginas) — o fluxo
  descrito (seção 2.10) mostra o documento sendo entregue completo direto pela distribuição, sem
  nenhum evento de "ciência" intermediário. **Ainda não é 100% certeza** (só teste real confirma
  de fato), mas é uma hipótese bem mais forte agora do que quando o plano foi escrito.
- **`cUFAutor`**: campo existe no schema com a mesma descrição da NF-e ("Código da UF do Autor")
  — ainda não testado com valor real.

## Decisão de arquitetura

**Módulo novo e separado** (`app/services/cte_client.py`), em vez de generalizar
`app/services/sefaz_client.py` num cliente parametrizado por tipo de documento.

Motivos:
- Só há 2 tipos de documento (NF-e e CT-e) — abstrair agora é especulativo (YAGNI)
- `sefaz_client.py` está em produção e testado ponta a ponta — mexer nele pra "abrir espaço" pro
  CT-e arrisca o fluxo real de compras sem necessidade
- A lógica de manifestação pode ser bem diferente (ou nem existir) pro CT-e — não dá pra desenhar
  uma abstração comum responsável antes de saber isso na Fase 0

**Reaproveitado por import direto, sem duplicar nem alterar `sefaz_client.py`:**
- `parse_status(xml_response)` — genérica o bastante, opera sobre `cStat`/`xMotivo`, estrutura
  compartilhada por todo o padrão nacional de Distribuição DFe
- Classes de exceção `SefazError`/`SefazNotFoundError` — são só marcadores de erro, sem estado
  específico de NF-e

**⚠️ Revisado pós-Fase 0**: `extract_documents(xml_response)` **não** é reaproveitável como estava
previsto — ela descarta o NSU de cada `docZip`, que a estratégia de paginação por `distNSU`
precisa pra saber onde continuar. `cte_client.py` implementa sua própria
`extract_documents_with_nsu()` (ver Fase 1) em vez de importar essa função.

---

## Fase 0 — Pesquisa e validação empírica (nenhum código de produção antes disso)

Script descartável `poc_consulta_cte.py` (raiz do projeto, mesmo padrão de `poc_consulta.py` —
segredos só via variável de ambiente).

- [x] Pesquisar documentação oficial (Nota Técnica do webservice `CTeDistribuicaoDFe`, portal
      nacional CT-e — **não** blog de fornecedor) e confirmar:
  - [x] URL de produção do webservice — ver "Achados confirmados" acima
  - [ ] Namespace do `distDFeInt` pro CT-e — **ainda não confirmado por leitura direta do XSD**
        (WSDL bloqueado por mTLS, igual à NF-e); hipótese por analogia forte de nome de método/
        estrutura de campos: `http://www.portalfiscal.inf.br/cte` — **testar empiricamente antes
        de assumir**, já erramos uma suposição de namespace análoga na Fase 0 da NF-e
  - [x] Nome da tag de consulta por chave — **não existe** (achado principal); usa-se `distNSU`
  - [ ] `cUFAutor`: ainda não testado com valor real (hipótese: mesmo valor já usado hoje, `"42"`)
  - [x] Se existe manifestação do tomador obrigatória — sem evidência na Nota Técnica primária
        (ver "Achados confirmados"), mas falta confirmação empírica
- [x] Conseguir uma chave de acesso real de CT-e — **conseguida em 18/08/2026**:
      `43260830800793000275570040000012651374168806` (empresa é destinatária **e** tomadora,
      emitida 12/08/2026). Validada localmente: 44 dígitos, DV módulo 11 correto, modelo `57`
      (posições 21-22) confirmando ser CT-e de fato, `cUF` do emitente `43` (RS), `AAMM` `2608`
      batendo com a data de emissão informada.
- [ ] Testar contra produção com o certificado real já em uso, usando `distNSU` com `ultNSU="0"`
      (não dá pra testar `consChCTe` — não existe) e procurar a chave acima no lote retornado
- [ ] Registrar `cStat`/`xMotivo`, quantos documentos vieram no primeiro lote, se a chave-alvo
      apareceu nesse lote ou se vai precisar paginar mais, estrutura do `docZip`
      **Resultado do teste:** _(preencher depois de rodar)_
- [ ] **Checkpoint já disparado, mas por motivo diferente do previsto**: não foi a manifestação
      (segue sem confirmação, mas com hipótese forte de que não existe) — foi a **ausência total
      de consulta por chave**, que já mudou o desenho da Fase 1 abaixo. Se o teste real do
      `distNSU` revelar um volume grande de documentos acumulados pra esse CNPJ/papel (ex:
      centenas antes de chegar na chave de agosto/2026), **parar e reavaliar a estratégia de
      paginação com o usuário** antes de seguir pra Fase 2 — pode ser inviável percorrer do zero
      toda vez.

**Pronto quando:** teste real contra produção com a chave acima retorna o documento completo
(direto ou após paginação), confirmando namespace, `cUFAutor`, comportamento de manifestação e
volume de paginação necessário — não só por documentação.

---

## Fase 1 — Cliente CT-e

Novo `app/services/cte_client.py`, espelhando `app/services/sefaz_client.py`:

```python
from app.services.sefaz_client import parse_status, extract_documents, SefazError, SefazNotFoundError
```

**Desenho revisado pós-Fase 0**: como não existe consulta direta por chave, `get_full_document`
não manda mais a chave no pedido — ele **pagina por `distNSU` e filtra client-side** até achar um
documento cuja `chCTe` bata com a chave procurada. Funções a implementar (URL confirmada na Fase 0;
namespace/`cUFAutor` a confirmar no teste real):

- [ ] `_build_envelope_dist_nsu(ult_nsu, profile) -> str` — monta o XML com a tag `distNSU`
      (substitui o `_build_envelope(access_key, ...)` do desenho original, que não se aplica mais)
- [ ] `query_dist_nsu(ult_nsu, profile) -> str` (`requests_pkcs12.post` contra `CTE_URL`)
- [ ] `extract_documents_with_nsu(xml_response) -> list[tuple[str, str]]` — **nova função**, não
      reaproveitada de `sefaz_client.py`: precisa devolver o par `(NSU, documento)` de cada
      `docZip` (o atributo `NSU` de cada item, ver campo `B12` da Nota Técnica), não só o
      documento — o `extract_documents()` existente descarta o NSU, que aqui é necessário pra
      paginar (`ultNSU` do próximo pedido)
- [ ] `parse_max_nsu(xml_response) -> str` — **nova função**, extrai o campo `maxNSU` (B09) da
      resposta, pra saber quando parar de paginar (chegou ao fim disponível)
- [ ] `extract_ch_cte(document_xml) -> str` — **nova função**, extrai a chave de acesso (`chCTe`
      ou campo equivalente confirmado no teste real) de dentro de um documento CT-e decodificado,
      pra comparar com a chave procurada
- [ ] `get_full_document(access_key, profile) -> str` — cooldown → percorre `distNSU` a partir de
      `ultNSU="0"` (ou de um NSU salvo, se decidirmos persistir isso depois — fora de escopo por
      ora) → em cada lote, procura a `chCTe` correspondente via `extract_ch_cte` → se achar,
      retorna; se o lote esgotar (`ultNSU` retornado == `maxNSU`) sem achar, `SefazNotFoundError`;
      lógica de manifestação só entra se o teste real confirmar que é necessária
- [ ] `get_full_document_any_cnpj(access_key) -> tuple[str, str]` — mesmo fallback entre
      `get_certificate_profiles()`

**Risco de performance não resolvido**: se a empresa tiver muitos documentos acumulados como
tomadora (CT-e nunca consultado nesse papel antes), achar uma chave de agosto/2026 pode exigir
paginar vários lotes de 50 a partir do início. Sem solução definida ainda — depende do volume real
que o teste da Fase 0 revelar.

**Reaproveitar sem alterar:**
- `app/services/rate_limiter.py` (`check_cooldown`/`register_not_found`) — chave já é
  `(cnpj, access_key)`, sem risco de colisão entre chaves de NF-e e CT-e (formatos de 44 dígitos
  nunca coincidem entre os dois). Regra de cooldown de 1h mantida por precaução mesmo sem
  confirmação explícita pra CT-e — custo de manter é zero
- `app/core/config.py` (`settings`, `CertificateProfile`, `get_certificate_profiles()`) — sem
  alteração, a não ser que a Fase 0 confirme `cUFAutor` diferente; nesse caso resolver dentro de
  `cte_client.py` (constante ou dict local por perfil), sem acoplar o dataclass genérico de
  certificado a um detalhe de CT-e
- `app/core/auth.py` (`verify_api_key`) e `app/core/logging_config.py` (`log_event`) —
  reaproveitados como estão; `logger = logging.getLogger("cte_client")`, logando só
  `access_key`/`profile`/`c_stat`
- `app/services/certificate.py` (`load_certificate`) — só entra em jogo se a manifestação de CT-e
  existir e precisar assinar XML

**Pronto quando:** `cte_client.get_full_document_any_cnpj("<chave real>")` retorna o XML completo,
testado manualmente (script/REPL) contra produção antes de ligar o endpoint HTTP.

---

## Fase 2 — Endpoint e schema

- [ ] Novo `app/schemas/cte.py` com `CTeQueryRequest`, reaproveitando o padrão de validação de
      `NFeQueryRequest` (`app/schemas/nfe.py`) e acrescentando checagem do modelo do documento
      (posições 21-22 da chave = `57` ou `67`), pra pegar cedo o erro de mandar uma chave de NF-e
      nesse endpoint por engano
- [ ] Novo endpoint em `app/main.py`, sem tocar nos endpoints de NF-e existentes:
      `POST /consultas/cte/xml`, seguindo exatamente o padrão de tratamento de erro já usado em
      `/consultas/xml` (`RateLimitError`→429, `SefazNotFoundError`→404, `SefazError`→502),
      devolvendo `Response(content=xml_document, media_type="application/xml")`
- [ ] Confirmar o nome do path com o usuário antes de fechar — escolhido como
      `/consultas/cte/xml` (em vez de `/consultas/cte`) pra deixar espaço a um futuro
      `/consultas/cte/json` sem quebrar compatibilidade; é decisão de gosto/convenção, não técnica

**Pronto quando:** `POST /consultas/cte/xml` com uma chave real de CT-e retorna XML 200, e os
erros mapeiam corretamente (404/429/502/422), testado contra produção.

---

## Fase 3 — Testes automatizados

Seguindo o padrão de `tests/test_nfe_parser.py`:

- [ ] `tests/fixtures/cte_proc_sample.xml` — XML real obtido na Fase 0 (anonimizado se necessário),
      pra testes não dependerem de rede
- [ ] `tests/test_cte_schema.py` — validação de `CTeQueryRequest` (aceita chave 44 dígitos com
      modelo 57/67, rejeita modelo 55, rejeita não-numérico/tamanho errado)
- [ ] `tests/test_cte_client.py` — `_build_envelope` gera XML com URL/tag/namespace corretos
      (teste de estrutura, sem rede). **Não** duplicar teste de `parse_status`/`extract_documents`
      (já cobertas em `sefaz_client.py`)
- [ ] Sem teste de parser estruturado — fora do escopo combinado

**Pronto quando:** `python -m pytest` passa sem exigir rede ou certificado real.

---

## Fase 4 — Documentação

- [ ] Novo `docs/protocolo-cte-sefaz.md`, mesmo espírito de `docs/protocolo-sefaz.md`: documentar
      URL, tag, `cUFAutor`, manifestação (ou ausência dela), marcando explicitamente qualquer ponto
      "não confirmado com certeza" — só registrar o que a Fase 0 validar de fato, não suposições
      deste plano
- [ ] Atualizar `TODO.md` com a nova Fase 0 (CT-e) no mesmo formato de checklist +
      "Resultado do teste"
- [ ] Atualizar `docs/estrutura-do-projeto.md` (árvore de pastas) e `README.md`
      (tabela de endpoints, com nota se o CT-e usa URL nacional diferente da de NF-e — relevante
      pra depuração de rede/firewall em produção)

---

## Fase 5 — Deploy/config

Provavelmente **sem alteração** em `.env`/`.env.example`/`k8s/deployment.yaml` — mesmos
certificados della/migra (mesmo `.pfx`/CNPJ) devem servir pro papel de tomador. Só muda se a
Fase 0 revelar `cUFAutor` diferente por tipo de documento e a decisão for expor isso via env var
(`CERT_DELLA_UF_AUTOR_CTE` etc., com fallback pro valor atual) em vez de constante no código.

---

## Riscos e incertezas em aberto (atualizado 18/08/2026)

**Resolvidos pela pesquisa documental:**
1. ~~URL do webservice CT-e~~ — confirmada, Ambiente Nacional (não SVRS)
2. ~~Nome da tag de consulta~~ — confirmado que **não existe** consulta por chave; usa-se `distNSU`
3. ~~Regra de cooldown (1h)~~ — confirmada oficialmente na Nota Técnica, não só por analogia

**Ainda em aberto, só teste real resolve:**
1. Namespace do `distDFeInt` pro CT-e (hipótese: `http://www.portalfiscal.inf.br/cte`)
2. `cUFAutor` correto pro CT-e (hipótese: mesmo valor da NF-e, `"42"`)
3. Necessidade de manifestação do tomador — evidência forte de que não existe (Nota Técnica não
   menciona), mas não é 100% certeza até o teste real
4. Mesmo e-CNPJ funcionando pros dois papéis (destinatário de NF-e e tomador de CT-e) —
   presumido, não confirmado
5. **Novo, descoberto na pesquisa**: volume de documentos acumulados pra paginar via `distNSU`
   até achar a chave de agosto/2026 — se for grande, a estratégia de "sempre começar do
   `ultNSU=0`" pode ser inviável e precisa de revisão (ex: persistir o último NSU visto)

## Arquivos críticos

| Arquivo | Papel |
|---|---|
| `app/services/sefaz_client.py` | Padrão a espelhar; fonte de `parse_status`, `extract_documents`, `SefazError`, `SefazNotFoundError` reaproveitados por import |
| `app/services/cte_client.py` (novo) | Fase 1 |
| `app/schemas/cte.py` (novo) | Fase 2 |
| `app/main.py` | Novo endpoint `POST /consultas/cte/xml`, sem alterar os existentes |
| `app/core/config.py` | Sem alteração esperada; ponto a confirmar na Fase 0 |
| `docs/protocolo-sefaz.md` | Modelo pra `docs/protocolo-cte-sefaz.md` |
| `TODO.md` | Onde registrar a Fase 0 do CT-e e seu resultado empírico antes de codar |

## Verificação end-to-end

- [ ] Rodar `poc_consulta_cte.py` contra produção com chave real → confirmar `cStat 138` (ou
      equivalente) e `docZip` decodificável
- [ ] Subir o serviço local (`uvicorn app.main:app`), chamar `POST /consultas/cte/xml` com
      `X-API-Key` válido e a mesma chave real → conferir XML 200 e conteúdo batendo com o
      `docZip` da Fase 0
- [ ] Testar caso de erro: chave inexistente/de outro CNPJ → 404; chave de NF-e (modelo 55) →
      422 (rejeitada pelo schema); repetir a mesma consulta antes de 1h após um 404 → 429
- [ ] `python -m pytest` — todos os testes (existentes + novos) passando