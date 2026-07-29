# TODO — API_Sefaz (serviço de consulta de NF-e via certificado digital)

Serviço isolado, em **Python**, separado do monolito `controleDeCompra`. Comunicação entre os
dois é via HTTP: o monolito manda um `POST` com a chave de acesso, este serviço consulta a
SEFAZ (webservice nacional **NFe Distribuição DFe**, autenticado por mTLS com o certificado
digital e-CNPJ da empresa) e devolve um JSON já tratado, pronto pro monolito usar.

Contexto/decisão completa (por que Distribuição DFe em vez de raspar HTML da SEFAZ-SC) está
registrada no `TODO.md` do `controleDeCompra`, seção "Semana 8" e "Notas de decisão em aberto".

Certificado disponível: **A1** (arquivo `.pfx`/`.p12`), e-CNPJ da empresa.

Marque cada item com `[x]` conforme for concluindo.

---

## Fase 0 — Provar que a consulta funciona (fazer ANTES de estruturar o serviço)

> Objetivo único desta fase: eliminar o risco de "construir tudo e descobrir no fim que não
> dá pra acessar os dados que preciso". Nada aqui precisa ser bonito ou definitivo — é só um
> script descartável (`poc_consulta.py`) rodando na sua máquina/VM de dev.

- [ ] Copiar o `.pfx` pra VM de dev, fora de qualquer pasta versionada pelo git (ex: `~/certs/`)
- [ ] Guardar a senha do certificado só em variável de ambiente local (nunca em texto no código ou em arquivo versionado)
- [ ] Inspecionar o certificado com `openssl pkcs12 -info -in certificado.pfx -noout` e conferir: CNPJ do titular bate com o da empresa, validade ainda não expirou, é e-CNPJ (não e-CPF)
- [ ] Instalar `cryptography` e escrever uma função curta que abre o `.pfx` (senha) e extrai o certificado + chave privada em memória (sem gravar `.pem` em disco, pra não vazar a chave por acidente)
- [ ] Montar uma sessão `requests`/`httpx` com esse certificado (via `ssl.SSLContext` carregado com cert+key, ou lib `requests-pkcs12` se simplificar) e testar contra o webservice de **Status do Serviço** da SEFAZ (endpoint simples, sem lógica de negócio) — objetivo aqui é só confirmar que o handshake mTLS funciona
- [ ] Pesquisar/confirmar a URL oficial do webservice nacional **NFeDistribuicaoDFe** (ambiente de produção) e o formato esperado do envelope SOAP (`distDFeInt`)
- [ ] Pegar a chave de acesso (44 dígitos) de uma nota que a empresa **realmente recebeu** de algum fornecedor (homologação não serve pra isso — não tem notas reais vinculadas ao CNPJ; o teste precisa ser em produção)
- [ ] Montar e enviar a consulta por chave (`consChNFe`) contra o ambiente de produção com essa chave real
- [ ] Confirmar se voltou o documento (`docZip`: base64 + gzip) e conseguir descompactar até o XML puro da nota
- [ ] Repetir o teste com 2-3 chaves diferentes (fornecedores diferentes, se possível) pra não tirar conclusão de um caso único
- [ ] **Checkpoint de decisão**: registrar aqui embaixo o resultado — se funcionou plenamente, se veio parcial, ou se algum erro apareceu (cert rejeitado, CNPJ não habilitado, chave não encontrada, limite de consultas, etc.) antes de seguir pra Fase 1

**Resultado do teste (preencher depois de rodar):**
- Data do teste: _—_
- Funcionou? _—_
- Observações / bloqueios encontrados: _—_

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
