# TODO — API_Sefaz (serviço de consulta de NF-e via certificado digital)

Serviço isolado, em **Python**, separado do monolito `controleDeCompra`. Comunicação entre os
dois é via HTTP: o monolito manda um `POST` com a chave de acesso, este serviço consulta a
SEFAZ (webservice nacional **NFe Distribuição DFe**, autenticado por mTLS com o certificado
digital e-CNPJ da empresa) e devolve um JSON já tratado, pronto pro monolito usar.

Contexto/decisão completa (por que Distribuição DFe em vez de raspar HTML da SEFAZ-SC) está
registrada no `TODO.md` do `controleDeCompra`, seção "Semana 8" e "Notas de decisão em aberto".

Certificado disponível: **A1** (arquivo `.pfx`/`.p12`), e-CNPJ da empresa.

📄 Documentação de arquitetura e protocolo (diagramas Mermaid): [`docs/arquitetura-geral.md`](docs/arquitetura-geral.md) (visão geral dos dois serviços) e [`docs/protocolo-sefaz.md`](docs/protocolo-sefaz.md) (regras da SEFAZ, ciclo de vida do documento, uso indevido).

Marque cada item com `[x]` conforme for concluindo.

---

## Fase 0 — Provar que a consulta funciona (fazer ANTES de estruturar o serviço)

> Objetivo único desta fase: eliminar o risco de "construir tudo e descobrir no fim que não
> dá pra acessar os dados que preciso". Nada aqui precisa ser bonito ou definitivo — é só um
> script descartável (`poc_consulta.py`) rodando na sua máquina/VM de dev.

- [x] Copiar o `.pfx` pra VM de dev, fora de qualquer pasta versionada pelo git (está em `~/Área de Trabalho/`, fora do repo)
- [x] Guardar a senha do certificado só em variável de ambiente local (nunca em texto no código ou em arquivo versionado)
- [x] Inspecionar o certificado com `openssl pkcs12 -info -in certificado.pfx -noout` e conferir: CNPJ do titular bate com o da empresa, validade ainda não expirou, é e-CNPJ (não e-CPF) — confirmado: e-CNPJ PJ A1, titular COMERCIO DE CEREAIS DELLA LTDA, CNPJ `82885781000103`, válido até **15/09/2026** (⚠️ vence em ~6 semanas — anotar renovação)
- [ ] Instalar `cryptography` e escrever uma função curta que abre o `.pfx` (senha) e extrai o certificado + chave privada em memória (sem gravar `.pem` em disco, pra não vazar a chave por acidente)
- [ ] Montar uma sessão `requests`/`httpx` com esse certificado (via `ssl.SSLContext` carregado com cert+key, ou lib `requests-pkcs12` se simplificar) e testar contra o webservice de **Status do Serviço** da SEFAZ (endpoint simples, sem lógica de negócio) — objetivo aqui é só confirmar que o handshake mTLS funciona
- [ ] Pesquisar/confirmar a URL oficial do webservice nacional **NFeDistribuicaoDFe** (ambiente de produção) e o formato esperado do envelope SOAP (`distDFeInt`)
- [ ] Pegar a chave de acesso (44 dígitos) de uma nota que a empresa **realmente recebeu** de algum fornecedor (homologação não serve pra isso — não tem notas reais vinculadas ao CNPJ; o teste precisa ser em produção)
- [ ] Montar e enviar a consulta por chave (`consChNFe`) contra o ambiente de produção com essa chave real
- [x] Confirmar se voltou o documento (`docZip`: base64 + gzip) e conseguir descompactar até o XML puro da nota — mTLS + schema OK, resposta bem formada da SEFAZ confirmada (`cStat`/`xMotivo` reconhecidos); pendente: achar uma chave que retorne `cStat 138` (documento localizado) pra validar o `docZip` em si
- [ ] Repetir o teste com 2-3 chaves diferentes (fornecedores diferentes, se possível) pra não tirar conclusão de um caso único
- [ ] **Checkpoint de decisão**: registrar aqui embaixo o resultado — se funcionou plenamente, se veio parcial, ou se algum erro apareceu (cert rejeitado, CNPJ não habilitado, chave não encontrada, limite de consultas, etc.) antes de seguir pra Fase 1

**Resultado do teste (preencher depois de rodar):**
- Data do teste: 30/07/2026
- Funcionou? Parcialmente — mTLS, certificado e URL de produção (`www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe`) confirmados funcionando; schema do envelope corrigido (namespace do `distDFeInt` precisa ser `http://www.portalfiscal.inf.br/nfe`, não o namespace do WSDL). Primeira chave testada voltou `cStat 137` (nenhum documento localizado) — investigando se é erro de digitação da chave, CNPJ (matriz/filial) errado, ou janela de retenção do documento.
- Observações / bloqueios encontrados: nenhum bloqueio estrutural até agora — o maior risco (não conseguir "conversar" com o serviço) está eliminado. Testadas 3 chaves reais/recentes com `consChNFe`, todas `cStat 137` (nenhum documento localizado). Teste via `distNSU` (a partir do NSU 0) confirmou `maxNSU: 6602` — o canal de distribuição TEM dados pra esse CNPJ (não é falta de habilitação).
- ⚠️ **Regra de protocolo confirmada (fonte: MOC/NT 2014.002, via busca)**: fazer uma nova consulta em **menos de 1 hora** depois de receber `cStat 137` (nenhum documento localizado) já conta como uso indevido e gera `cStat 656`, bloqueando novas consultas por 1h. Não tem relação com "pular NSU" (isso foi engano nosso na investigação, corrigido aqui). Implicação pro serviço real: implementar um intervalo mínimo de 1h entre consultas malsucedidas pro mesmo CNPJ, e tratar `cStat 656` como "aguarde e tente depois", não como erro fatal.
- ✅ **Explicação confirmada de por que as 3 chaves testadas via `consChNFe` não foram encontradas**: a disponibilização de documentos só vale a partir do **primeiro acesso ao serviço** — documentos emitidos *antes* desse primeiro acesso não ficam disponíveis retroativamente, só os emitidos a partir dele. Como 30/07/2026 foi o primeiro acesso desse certificado/CNPJ, as notas testadas (emitidas antes) nunca estariam disponíveis. Não é falha do certificado/integração — próximo teste válido precisa ser com uma nota emitida **depois** de hoje.
- ⚠️ **Requisito de escopo novo, descoberto na pesquisa**: antes de enviar o evento de **Manifestação do Destinatário** ("Ciência da Operação", "Confirmação da Operação" ou "Operação não Realizada"), só fica disponível o **Resumo da NF-e** (dados básicos) — o XML completo com itens só libera depois da manifestação. Isso significa que o `API_Sefaz` provavelmente vai precisar **enviar esse evento de manifestação**, não só consultar — adicionar isso como tarefa na Fase 2/3 antes de fechar o design da API.

---

## Fase 1 — Estrutura do projeto Python

> Só começar depois da Fase 0 dar sinal verde.

- [ ] Escolher gerenciador de ambiente/pacotes (`uv` recomendado — rápido e moderno; `venv` + `pip` também resolve se preferir algo mais simples/familiar)
- [ ] Framework web: **FastAPI** (tipagem com Pydantic, docs automáticas em `/docs`, assíncrono — combina bem com chamadas de rede pra SEFAZ)
- [ ] Estrutura de pastas inicial: `app/` (`api/`, `services/`, `schemas/`, `core/`), `tests/`
- [ ] `.env.example` com as variáveis necessárias (caminho do `.pfx`, senha do certificado, ambiente SEFAZ produção/homologação, porta do serviço)
- [ ] `.gitignore` (venv, `__pycache__`, `.env`, e explicitamente qualquer `*.pfx`/`*.p12` — nunca commitar certificado)
- [ ] `GET /health` simples pra validar que o serviço sobe

## Fase 2 — Cliente SEFAZ (core da integração)

- [ ] Módulo de certificado: carregar o `.pfx` uma vez na inicialização (cache em memória), sem re-ler do disco a cada requisição
- [ ] Cliente SOAP (`zeep` ou envelope manual com `httpx`) configurado com o certificado pra falar com o `NFeDistribuicaoDFe`
- [ ] Função `consultar_por_chave(chave: str)` que monta o `consChNFe`, envia e recebe a resposta
- [ ] Descompactar `docZip` (base64 + gzip) e parsear o XML da nota (`lxml` ou `xmltodict`) extraindo: emitente (CNPJ, nome), itens (produto, quantidade, valor unitário, valor total), valor total da nota, data de emissão
- [ ] Tratar os casos de retorno sem sucesso da própria SEFAZ (cStat diferente de sucesso: nota não encontrada, chave inválida, ambiente errado) mapeando pra mensagens claras
- [ ] Implementar o envio do evento de **Manifestação do Destinatário** (`envEvento`/`RecepcaoEvento`, tipo "Ciência da Operação") — descoberto na Fase 0: sem isso, só o Resumo da NF-e fica disponível, não o XML completo com os itens
- [ ] Respeitar o intervalo mínimo de 1h entre novas consultas depois de um `cStat 137` (regra de uso indevido descoberta na Fase 0) — implementar esperando/avisando, não tratando como erro fatal

## Fase 3 — Contrato da API (o que o monolito consome)

- [ ] Definir o schema Pydantic da resposta: o que veio automaticamente da SEFAZ vs. o que precisa ficar em branco pra preenchimento manual no formulário
- [ ] `POST /consultas/nfe` — recebe `{ chaveAcesso: string }`, devolve o JSON tratado (ou erro claro e padronizado)
- [ ] Tratamento de erros HTTP consistente: certificado inválido/expirado, timeout de rede, nota não encontrada, chave malformada — sempre com corpo de erro previsível pro monolito conseguir tratar
- [ ] Testes automatizados dos parsers usando XMLs de exemplo salvos localmente (sem depender de bater na SEFAZ real a cada rodada de teste)

## Fase 4 — Integração com o monolito

- [ ] Subir o serviço no `docker-compose.yml` da raiz (`sistema_de_compras`), na mesma rede interna do `controleDeCompra`, sem expor porta pra fora
- [ ] Decidir autenticação entre serviços (API key simples num header, já que é rede interna — não precisa de algo mais pesado)
- [ ] No backend do monolito, criar o client HTTP que chama `POST /consultas/nfe` do `API_Sefaz` e mapeia a resposta pro fluxo de pré-preenchimento do formulário (reaproveitando o padrão de `supplierPicker.create`/`productPicker.create` já usado no lançamento manual)
- [ ] Teste ponta a ponta: escanear/informar uma chave real no frontend → monolito chama `API_Sefaz` → formulário pré-preenchido

## Fase 5 — Polish

- [ ] Logs estruturados (sem logar a senha do certificado ou o conteúdo sensível da nota em texto puro)
- [ ] `Dockerfile` de produção (imagem Python enxuta, ex: `python:3.12-slim`)
- [ ] README do serviço: como rodar local, como configurar o certificado, variáveis de ambiente

---

## Notas de decisão

- **Linguagem**: ✅ decidido em 29/07/2026 — **Python**, isolado do monolito TypeScript. Vale a pena porque a integração depende de SOAP + assinatura XML + certificado PKCS12, área onde o ecossistema Python (`zeep`, `signxml`, `cryptography`, projetos de referência como `nfelib`) é bem mais maduro que o equivalente em Node. Comunicação entre os dois serviços é só HTTP/JSON, então a escolha de linguagem fica isolada e de baixo risco.
- **Framework web**: sugestão **FastAPI** (ainda não confirmado com o usuário — trocar por Flask se preferir algo mais simples, não muda o resto do plano).
- **Ambiente de teste**: consulta real só funciona em **produção** — homologação da SEFAZ não tem notas reais emitidas contra o CNPJ da empresa.
