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
  - [x] Namespace do `distDFeInt` pro CT-e — **confirmado empiricamente em 21/08/2026**:
        `http://www.portalfiscal.inf.br/cte` estava certo de primeira (`cStat 138`, sem erro de
        schema). Namespace do wrapper WSDL também certo:
        `http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe`, com o elemento de dados
        chamado `cteDadosMsg` (por analogia ao `nfeDadosMsg` da NF-e) — não precisou iterar
  - [x] Nome da tag de consulta por chave — **não existe** (achado principal); usa-se `distNSU`
  - [x] `cUFAutor`: **testado com valor real em 21/08/2026** — `"42"` foi aceito sem reclamação
        (mesma hipótese da NF-e confirmada)
  - [ ] Se existe manifestação do tomador obrigatória — **ainda não 100% confirmado, achado
        matizado em 21/08/2026**: o documento de teste voltou completo (`cteProc` com `infCte`
        inteiro), mas **o teste não distingue "não existe manifestação" de "esse CT-e específico
        já foi manifestado/consultado antes por outro sistema"** (ex: programa do contador) — se
        um terceiro com acesso ao mesmo CNPJ já consumiu esse NSU antes, o `distNSU` devolveria o
        documento completo de qualquer forma, independente de existir a exigência. Busca por um
        schema de "resumo" tipo `resCTe` (análogo ao `resNFe_v1.01.xsd` da NF-e, que é o sinal
        formal desse estado pré-manifestação) não achou nenhuma menção em fontes técnicas
        (wikis SVRS/unimake, Nota Técnica) — evidência indireta a favor de "não existe", mas não
        conclusiva. **Decisão prática**: não vale insistir em provar isso por pesquisa, e também
        não vale inventar um mecanismo de detecção/envio de manifestação sem saber o schema/evento
        real do CT-e — o `cte_client.py` só faz uma checagem de sanidade (documento reconhecível
        como `cteProc`/`CTe` ou erro claro), sem tentar automatizar uma manifestação que não foi
        pesquisada (ver Fase 1 revisada).
- [x] Conseguir uma chave de acesso real de CT-e — **conseguida em 18/08/2026**:
      `43260830800793000275570040000012651374168806` (empresa é destinatária **e** tomadora,
      emitida 12/08/2026). Validada localmente: 44 dígitos, DV módulo 11 correto, modelo `57`
      (posições 21-22) confirmando ser CT-e de fato, `cUF` do emitente `43` (RS), `AAMM` `2608`
      batendo com a data de emissão informada. **Segunda chave usada no teste real (21/08/2026)**:
      `43260830800793000275570040000013051150732250` — mesmo emitente/série, `nCT` mais recente
      (1305); também validada localmente (DV ok, modelo 57) antes do teste.
- [x] Testar contra produção com o certificado real já em uso, usando `distNSU` com `ultNSU="0"`
      (não dá pra testar `consChCTe` — não existe) e procurar a chave acima no lote retornado
- [x] Registrar `cStat`/`xMotivo`, quantos documentos vieram no primeiro lote, se a chave-alvo
      apareceu nesse lote ou se vai precisar paginar mais, estrutura do `docZip`
      **Resultado do teste (21/08/2026, script `poc_consulta_cte.py`, cert migra):**
      - `cStat 138` / `xMotivo "documento localizado."` logo no primeiro request — confirma
        namespace, versão (`1.00`) e `cUFAutor` de uma vez
      - **Achado não previsto**: com `ultNSU="0"`, o primeiro lote retornado não começou no NSU 1,
        e sim no NSU 3599 (`maxNSU` total nesse momento: 4088). Ou seja, pra esse CNPJ/papel já
        existem ~3598 NSUs "anteriores" que a SEFAZ não devolveu — hipótese mais provável: janela
        de retenção do buffer de distribuição (documentos/eventos mais antigos não ficam
        disponíveis pra sempre via `distNSU`, só os mais recentes). Não é erro do cliente, o
        `cStat` veio de sucesso; não afeta o caso de uso atual (só precisamos de chaves recentes),
        mas é bom registrar caso o volume de retenção mude no futuro.
      - Cada lote veio com exatamente 50 `docZip`, mistura de CT-e de várias transportadoras
        diferentes **e** eventos (`schema="procEventoCTe_v4.00.xsd"` — cancelamento/EPEC etc.,
        sem `Id="CTe..."` porque não são o CT-e em si)
      - A chave-alvo apareceu no **8º lote** (NSU 4046 de 4088), depois de paginar a partir do
        NSU 3648 — total de ~9 lotes de 50 desde o início disponível até achar, volume plenamente
        gerenciável, não bateu no alerta de "parar e reavaliar"
      - Documento retornado: `<cteProc versao="4.00">` completo, com `infCte`, `ide`, dados de
        frete/veículo/motorista/seguro no `xObs`, `emit` — sem truncamento nem placeholder
- [x] **Checkpoint disparado, resolvido**: não foi a manifestação (segue sem confirmação 100%,
      mas contornada pela decisão de código defensivo — ver item acima) — foi a **ausência total
      de consulta por chave**, que já mudou o desenho da Fase 1. O volume real de paginação
      (~9 lotes pra achar uma chave de agosto/2026, a partir do NSU disponível mais antigo) é
      gerenciável, então **não é necessário reavaliar a estratégia** — segue pra Fase 1 como
      desenhada.

**Pronto quando:** teste real contra produção com a chave acima retorna o documento completo
(direto ou após paginação), confirmando namespace, `cUFAutor` e volume de paginação necessário —
não só por documentação. Comportamento de manifestação fica sem confirmação 100% (ver ressalva
acima), mas isso não bloqueia a Fase 0: o código vai lidar com as duas hipóteses defensivamente.
**✅ Fase 0 concluída em 21/08/2026.**

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

- [x] `_build_envelope_dist_nsu(ult_nsu, profile) -> str` — monta o XML com a tag `distNSU`
      (substitui o `_build_envelope(access_key, ...)` do desenho original, que não se aplica mais)
- [x] `query_dist_nsu(ult_nsu, profile) -> str` (`requests_pkcs12.post` contra `CTE_URL`)
- [x] `extract_documents_with_nsu(xml_response) -> list[tuple[str, str]]` — **nova função**, não
      reaproveitada de `sefaz_client.py`: precisa devolver o par `(NSU, documento)` de cada
      `docZip` (o atributo `NSU` de cada item, ver campo `B12` da Nota Técnica), não só o
      documento — o `extract_documents()` existente descarta o NSU, que aqui é necessário pra
      paginar (`ultNSU` do próximo pedido)
- [x] `parse_max_nsu(xml_response) -> str` — **nova função**, extrai o campo `maxNSU` (B09) da
      resposta, pra saber quando parar de paginar (chegou ao fim disponível)
- [x] `extract_ch_cte(document_xml) -> str` — **nova função**, extrai a chave de acesso de dentro
      de um documento CT-e decodificado, pra comparar com a chave procurada. **Confirmado no teste
      real (21/08/2026)**: não existe uma tag `<chCTe>` separada — a chave vem no atributo
      `Id="CTe" + 44 dígitos` do elemento `<infCte>` (`<infCte Id="CTe4326...">`), mesmo padrão do
      `Id="NFe" + 44 dígitos` da NF-e. Também precisa ignorar documentos que são eventos
      (`schema="procEventoCTe_*.xsd"`, sem esse atributo) em vez de tratar como erro
- [x] `get_full_document(access_key, profile) -> str` — cooldown → percorre `distNSU` a partir de
      `ultNSU="0"` (ou de um NSU salvo, se decidirmos persistir isso depois — fora de escopo por
      ora) → em cada lote, procura a `chCTe` correspondente via `extract_ch_cte` → se achar,
      retorna; se o lote esgotar (`ultNSU` retornado == `maxNSU`) sem achar, `SefazNotFoundError`.
      **Manifestação: NÃO implementar detecção/envio de evento** — a pesquisa não achou schema de
      resumo (`resCTe` ou equivalente) pro CT-e, então não há o que checar/disparar sem inventar um
      mecanismo sem base. Em vez de um "raise" que finge certeza (se um resumo desconhecido não
      tiver a chave no formato `Id="CTe..."`, o próprio `extract_ch_cte` já não acharia a chave-alvo
      nele, e o `raise` nunca dispararia de verdade — proteção decorativa), fica só um **log de
      aviso** se o documento encontrado vier suspeitosamente curto (abaixo de um tamanho mínimo
      observado no teste real) — sinal fraco, sem travar o fluxo, útil só como pista futura
- [x] `get_full_document_any_cnpj(access_key) -> tuple[str, str]` — mesmo fallback entre
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

**✅ Fase 1 concluída em 21/08/2026.** Testado via REPL contra produção:
`get_full_document_any_cnpj("43260830800793000275570040000013051150732250")` → achou de primeira
no perfil **della** (nem precisou do fallback pra migra), `<cteProc>` completo de 8863 caracteres,
bem acima do limiar de aviso de tamanho mínimo. `.env` local criado com os campos da della
preenchidos de verdade e os da migra como placeholder (não tocado nesse teste, máquina atual só
tem o certificado da della disponível).

---

## Fase 2 — Endpoint e schema

- [x] Novo `app/schemas/cte.py` com `CTeQueryRequest`, reaproveitando o padrão de validação de
      `NFeQueryRequest` (`app/schemas/nfe.py`) e acrescentando checagem do modelo do documento
      (posições 21-22 da chave = `57` ou `67`), pra pegar cedo o erro de mandar uma chave de NF-e
      nesse endpoint por engano
- [x] Novo endpoint em `app/main.py`, sem tocar nos endpoints de NF-e existentes:
      `POST /consultas/cte/xml`, seguindo exatamente o padrão de tratamento de erro já usado em
      `/consultas/xml` (`RateLimitError`→429, `SefazNotFoundError`→404, `SefazError`→502),
      devolvendo `Response(content=xml_document, media_type="application/xml")`
- [x] Confirmar o nome do path com o usuário antes de fechar — escolhido como
      `/consultas/cte/xml` (em vez de `/consultas/cte`) pra deixar espaço a um futuro
      `/consultas/cte/json` sem quebrar compatibilidade; é decisão de gosto/convenção, não técnica

**Pronto quando:** `POST /consultas/cte/xml` com uma chave real de CT-e retorna XML 200, e os
erros mapeiam corretamente (404/429/502/422), testado contra produção.

**✅ Fase 2 concluída em 21/08/2026.** Testado via `curl` contra o servidor local (`uvicorn`),
apontando pra produção de verdade da SEFAZ:
- `POST /consultas/cte/xml` com a chave-alvo → `200`, XML completo (8863 bytes), `cStat 100`
  ("Autorizado o uso do CT-e") dentro do `protCTe`
- Bônus não planejado: testei sem querer com outra chave de CT-e real (transportadora diferente,
  mesma destinatária della) → também `200`, prova que o endpoint generaliza bem além da chave
  original de teste
- `POST /consultas/cte/xml` com uma chave de NF-e real (modelo `55`) → `422`, rejeitada pelo
  `CTeQueryRequest` antes de qualquer chamada à SEFAZ

---

## Fase 3 — Testes automatizados

Seguindo o padrão de `tests/test_nfe_parser.py`:

- [x] `tests/fixtures/cte_proc_sample.xml` — **não** é o XML bruto real (esse tem CPF/nome do
      motorista, certificado digital completo etc. — dado sensível demais pra ir pro Git); versão
      trimmed/reconstruída à mão, mantendo a estrutura e a chave de acesso real validada na Fase 0
- [x] `tests/test_cte_schema.py` — validação de `CTeQueryRequest` (aceita chave 44 dígitos com
      modelo 57/67, rejeita modelo 55, rejeita não-numérico/tamanho errado)
- [x] `tests/test_cte_client.py` — `_build_envelope_dist_nsu` gera XML com URL/tag/namespace
      corretos (teste de estrutura, sem rede), `extract_ch_cte`/`parse_max_nsu`/`parse_ult_nsu`
      testados contra a fixture. **Não** duplicado teste de `parse_status` (já coberto onde foi
      criado, em `sefaz_client.py`); `query_dist_nsu` deixado de fora por exigir rede real
- [x] Sem teste de parser estruturado — fora do escopo combinado

**Pronto quando:** `python -m pytest` passa sem exigir rede ou certificado real.

**✅ Fase 3 concluída em 21/08/2026.** 10 testes novos, todos verdes.

---

## Fase 4 — Documentação

- [x] Novo `docs/protocolo-cte-sefaz.md`, mesmo espírito de `docs/protocolo-sefaz.md`: documentar
      URL, tag, `cUFAutor`, manifestação (ou ausência dela), marcando explicitamente qualquer ponto
      "não confirmado com certeza" — só registrar o que a Fase 0 validar de fato, não suposições
      deste plano
- [x] Atualizar `TODO.md` com a nova Fase 6 (CT-e) no mesmo formato de checklist +
      "Resultado do teste"
- [x] Atualizar `docs/estrutura-do-projeto.md` (árvore de pastas) e `README.md`
      (tabela de endpoints, com nota de que o CT-e usa URL nacional diferente da de NF-e)

**✅ Fase 4 concluída em 21/08/2026.**

---

## Fase 5 — Deploy/config

Provavelmente **sem alteração** em `.env`/`.env.example`/`k8s/deployment.yaml` — mesmos
certificados della/migra (mesmo `.pfx`/CNPJ) devem servir pro papel de tomador. Só muda se a
Fase 0 revelar `cUFAutor` diferente por tipo de documento e a decisão for expor isso via env var
(`CERT_DELLA_UF_AUTOR_CTE` etc., com fallback pro valor atual) em vez de constante no código.

**✅ Confirmado em 21/08/2026**: sem alteração necessária. `cUFAutor` "42" funcionou igual pro
CT-e (não precisou de valor separado por tipo de documento). `k8s/deployment.yaml` já expõe
`CERT_DELLA_*`/`CERT_MIGRA_*` completos, reaproveitados como estão pelo `cte_client.py`. Nenhuma
dependência Python nova foi adicionada (`re`/`base64`/`gzip`/`logging` são biblioteca padrão;
`requests`/`requests_pkcs12` já estavam em uso). Próximo deploy real (build + push + rollout) fica
pendente só como rotina de deploy, não como trabalho de configuração.

---

## Riscos e incertezas em aberto (atualizado 21/08/2026)

**Resolvidos pela pesquisa documental (18/08/2026):**
1. ~~URL do webservice CT-e~~ — confirmada, Ambiente Nacional (não SVRS)
2. ~~Nome da tag de consulta~~ — confirmado que **não existe** consulta por chave; usa-se `distNSU`
3. ~~Regra de cooldown (1h)~~ — confirmada oficialmente na Nota Técnica, não só por analogia

**Resolvidos por teste real contra produção (21/08/2026):**
4. ~~Namespace do `distDFeInt` pro CT-e~~ — confirmado `http://www.portalfiscal.inf.br/cte`, certo
   de primeira
5. ~~`cUFAutor` correto pro CT-e~~ — confirmado `"42"`, mesmo valor da NF-e
6. ~~Volume de documentos acumulados pra paginar~~ — ~9 lotes de 50 (a partir do NSU mais antigo
   ainda disponível) pra achar uma chave de agosto/2026; plenamente gerenciável, não precisa de
   estratégia de persistência de NSU por enquanto

**Ainda em aberto:**
1. **Necessidade de manifestação do tomador — NÃO resolvido, apesar do teste real.** O documento
   de teste voltou completo, mas o teste é confundido pela possibilidade de outro sistema (ex:
   programa do contador) já ter consultado/manifestado esse CT-e antes de nós — nesse caso o
   `distNSU` devolveria o documento completo de qualquer forma, exista ou não a exigência. Sem
   evidência de um schema tipo `resCTe` em fontes técnicas, o que pesa a favor de "não existe",
   mas não é conclusivo. **Não bloqueia a Fase 1**: decisão é implementar a checagem defensiva
   sempre (mesmo padrão do NF-e), então o código funciona certo nas duas hipóteses
2. Mesmo e-CNPJ funcionando pros dois papéis (destinatário de NF-e e tomador de CT-e) —
   presumido, não confirmado (o teste usou o certificado migra; não foi testado com della)
3. **Novo, descoberto no teste real**: o `distNSU` com `ultNSU="0"` não retornou a partir do NSU 1
   — o primeiro NSU disponível já era 3599 (de um total `maxNSU` 4088 no momento do teste).
   Hipótese: janela de retenção do buffer de distribuição da SEFAZ. Não bloqueia o caso de uso
   atual, mas vale monitorar se o comportamento mudar

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

- [x] Rodar `poc_consulta_cte.py` contra produção com chave real → confirmado `cStat 138` e
      `docZip` decodificável (21/08/2026)
- [x] Subir o serviço local (`uvicorn app.main:app`), chamar `POST /consultas/cte/xml` com
      `X-API-Key` válido e a mesma chave real → `200`, XML completo batendo com o teste da Fase 0
- [x] Testar caso de erro: chave de NF-e (modelo 55) → `422` (rejeitada pelo schema, confirmado).
      **Não testado**: chave inexistente/de outro CNPJ → `404`, e repetição antes de 1h → `429`
      (ambos reaproveitam código já validado em produção pro NF-e — `SefazNotFoundError`/
      `rate_limiter.RateLimitError` são as mesmas classes, mesma lógica — risco residual baixo,
      mas fica registrado como não testado de fato pro CT-e especificamente)
- [x] `python -m pytest` — todos os testes (existentes + novos) passando, 13 no total