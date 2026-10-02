# Protocolo NFS-e Nacional (Ambiente de Dados Nacional — ADN)

Notas de uso da API de distribuição do ADN, baseadas no que foi validado no `TODONFSE.md`
(pesquisa documental + Swagger oficial + teste real contra produção em 02/10/2026). Mesmo
espírito do [`protocolo-sefaz.md`](protocolo-sefaz.md) (NF-e) e
[`protocolo-cte-sefaz.md`](protocolo-cte-sefaz.md) (CT-e): registrar aqui pra ninguém precisar
redescobrir.

⚠️ Onde não temos 100% de certeza, está marcado explicitamente como "não confirmado" — ver
`TODONFSE.md` pro raciocínio completo por trás de cada achado.

---

## 1. Diferença estrutural grande em relação à NF-e e ao CT-e: é REST/JSON, não SOAP

NF-e e CT-e falam com a SEFAZ via SOAP (`NFeDistribuicaoDFe`/`CTeDistribuicaoDFe`). A NFS-e
Nacional usa uma **API REST/JSON** completamente separada, no **Ambiente de Dados Nacional
(ADN)**, que trata o compartilhamento de documentos fiscais de serviço entre municípios (padrão
nacional, Lei Complementar 214/2025). Não existe envelope SOAP, não existe `cStat`/`xMotivo` no
nível de transporte — os erros vêm como status HTTP + um corpo JSON próprio (ver seção 4).

## 2. Igual ao CT-e num ponto importante: não existe consulta direta por chave

Confirmado pelo **Swagger oficial** (baixado autenticado da sandbox com o certificado della,
`GET /contribuintes/swagger/v1/swagger.json`) — só existem dois métodos:

| Método | Path | Uso |
|---|---|---|
| `GET` | `/DFe/{NSU}` | Lote de até 50 documentos a partir de um NSU — **única forma de achar um documento específico** |
| `GET` | `/NFSe/{ChaveAcesso}/Eventos` | Eventos (cancelamento etc.) vinculados a uma chave — não devolve o documento principal |

Igual ao CT-e: achar uma NFS-e por chave de acesso é busca client-side, paginando `/DFe/{NSU}`.
**Diferença que simplifica**: cada item do lote já traz a `ChaveAcesso` como campo próprio no
JSON — não precisa decodificar o XML antes de comparar com a chave procurada (no CT-e, é preciso
decodificar o `docZip` e extrair a chave do atributo `Id="CTe..."` antes de poder comparar).

## 3. Endpoint e autenticação confirmados (teste real, 02/10/2026)

| Item | Valor |
|---|---|
| URL produção | `https://adn.nfse.gov.br/contribuintes` |
| URL produção restrita (sandbox) | `https://adn.producaorestrita.nfse.gov.br/contribuintes` |
| Autenticação | mTLS, certificado ICP-Brasil A1/A3 com "Autenticação do Cliente" — **mesmo certificado já usado** pra NF-e/CT-e, sem credenciamento prévio extra |
| `cUFAutor` (ou equivalente) | **Não existe** — a chave já carrega o município (campo `cLocIncid` no XML), não precisa de UF do autor |

A consulta aceita certificado cujo CNPJ raiz bata com o contribuinte consultado (emitente, tomador
ou intermediário). Testado com o certificado della: `200 OK` de primeira, sem nenhum passo de
credenciamento no portal do ADN.

## 4. Formato da resposta (`LoteDistribuicaoNSUResponse`)

```json
{
  "StatusProcessamento": "DOCUMENTOS_LOCALIZADOS",
  "LoteDFe": [
    {
      "NSU": 131,
      "ChaveAcesso": "42046082212942976000162000000000558126108153219373",
      "TipoDocumento": "NFSE",
      "ArquivoXml": "H4sIAAAAAAAAA8V...",
      "DataHoraGeracao": "2026-10-01T22:10:17.3"
    }
  ],
  "Alertas": [],
  "Erros": [],
  "TipoAmbiente": "PRODUCAO",
  "VersaoAplicativo": "1.0.0.0",
  "DataHoraProcessamento": "2026-10-02T13:40:00"
}
```

- `StatusProcessamento`: `REJEICAO` | `NENHUM_DOCUMENTO_LOCALIZADO` | `DOCUMENTOS_LOCALIZADOS` —
  análogo ao `cStat` 137/138 da NF-e/CT-e, mas aqui é um enum de string, não um código numérico
- **"Não encontrado" vem como HTTP `404`** (confirmado: `NENHUM_DOCUMENTO_LOCALIZADO` com
  `Erros: [{"Codigo": "E2220", "Descricao": "Nenhum documento localizado..."}]`) — diferente de
  NF-e/CT-e, que sempre respondem `200` e colocam o status dentro do XML. **Precisa checar o
  status HTTP, não só o corpo.**
- `ArquivoXml`: gzip + base64 — mesmo padrão de empacotamento do `docZip` da NF-e/CT-e, só que
  aqui já vem solto no JSON, não dentro de um envelope SOAP
- `TipoAmbiente` (`PRODUCAO`/`HOMOLOGACAO`) é útil pra confirmar que a chamada caiu no ambiente
  certo (sandbox vs produção real)

## 5. Paginação por NSU — confirmada mais simples que o CT-e

`GET /DFe/{N}` devolve até 50 itens com `NSU > N` (não repete o item `N`). Pra continuar, basta
chamar de novo com `N = maior NSU do lote anterior`. **Sem o susto de "janela de retenção" que o
CT-e teve** (lá o primeiro `distNSU` não começava do NSU 1) — no teste real, `GET /DFe/0` já
devolveu a partir do NSU 1.

**Volume observado**: achar uma chave de 01/10/2026 levou **3 lotes de 50** (NSU 1→131) — bem
mais rápido que os ~9 lotes do CT-e pra uma chave de um mês antes. `nfse_client.py` usa o mesmo
`MAX_NSU_BATCHES = 100` do `cte_client.py` como trava de segurança, sem persistir o último NSU
visto entre chamadas (mesma decisão consciente de YAGNI).

## 6. Formato da chave de acesso (50 dígitos)

Diferente de NF-e/CT-e (44 dígitos). Composição confirmada por decodificação de uma chave real:

| Campo | Posições | Exemplo (chave real da Della) |
|---|---|---|
| Código do Município (IBGE) | 1–7 | `4204608` (Criciúma-SC) |
| Ambiente de Geração | 8 | `2` |
| Tipo de Inscrição Federal | 9 | `2` (CNPJ) |
| Inscrição Federal (do emitente) | 10–23 | `12942976000162` |
| Número da NFS-e | 24–36 | `0000000005581` |
| Ano/Mês de emissão | 37–40 | `2610` (out/2026) |
| Código Numérico | 41–49 | `815321937` |
| Dígito Verificador | 50 | `3` |

⚠️ **Algoritmo do dígito verificador ainda não identificado** — não é módulo 11 (testado, não
fechou). `app/schemas/nfse.py` valida só o tamanho (50 dígitos numéricos), sem recalcular o DV —
mesmo nível de rigor que os outros schemas tinham antes de aprenderem a checar o modelo do
documento.

Dentro do XML, a chave aparece no atributo `Id` do elemento `infNFSe`, com o prefixo `NFS`:
`Id="NFS" + 50 dígitos` — mesmo padrão do `Id="NFe"+chave`/`Id="CTe"+chave` da NF-e/CT-e.

## 7. Manifestação do tomador — não se aplica (nenhuma menção encontrada)

Nenhuma menção a manifestação/ciência da operação no manual oficial nem no Swagger — o documento
retornado pelo teste real já veio completo e autorizado (`cStat 100` dentro do XML). Diferente do
CT-e (onde isso ficou sem confirmação 100%), aqui a ausência de manifestação parece ser por
desenho da API em si (focada em distribuição simples), não só falta de evidência. `nfse_client.py`
não tenta detectar/enviar nenhum evento.

## 8. Regra de cooldown/anti-abuso — não documentada

Não achamos nenhuma menção, nem no manual de 3 páginas nem no Swagger. Aplicamos, por precaução,
o mesmo cooldown de 1h do `rate_limiter.py` usado pra NF-e/CT-e — sem confirmação oficial de que
é essa a regra real da ADN (pode ser mais permissiva ou mais restritiva).

## 9. Referências

- [Manual dos Contribuintes — APIs ADN Sistema Nacional NFS-e (gov.br/nfse)](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf)
- Swagger oficial (requer certificado válido): `https://adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html` (sandbox) / `https://adn.nfse.gov.br/contribuintes/swagger/v1/swagger.json` (spec OpenAPI)
- `TODONFSE.md` — raciocínio completo, incluindo a correção de uma suposição inicial errada (achávamos que existia consulta direta por chave)
- [`protocolo-sefaz.md`](protocolo-sefaz.md) / [`protocolo-cte-sefaz.md`](protocolo-cte-sefaz.md) — equivalentes pra NF-e/CT-e, cooldown compartilhado
