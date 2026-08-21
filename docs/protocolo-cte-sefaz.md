# Protocolo SEFAZ — CT-e (Distribuição DFe)

Notas de uso do webservice nacional `CTeDistribuicaoDFe`, baseadas no que foi validado no
`TODOCTE.md` (pesquisa documental + teste real contra produção em 21/08/2026). Mesmo espírito do
[`protocolo-sefaz.md`](protocolo-sefaz.md) (NF-e): registrar aqui pra ninguém precisar redescobrir.

⚠️ Onde não temos 100% de certeza, está marcado explicitamente como "não confirmado" — ver
`TODOCTE.md` pro raciocínio completo por trás de cada achado.

---

## 1. Diferença estrutural em relação à NF-e: não existe consulta por chave

A NF-e tem `consChNFe` (consulta pontual por chave de acesso). O CT-e **não tem equivalente**
(`consChCTe` não existe) — confirmado tanto pela Nota Técnica 2015/002 (12 páginas, nenhuma menção)
quanto por pesquisa adicional sobre provedores comerciais (nenhum contradiz isso; os que anunciam
"busca por chave" fazem por trás exatamente a estratégia abaixo, produtizada).

O schema `distDFeInt` do CT-e só aceita:

| Tag | Uso |
|---|---|
| `distNSU` | Lote de até 50 documentos a partir de um `ultNSU`, em ordem crescente — **única opção pra achar uma chave específica** |
| `consNSU` | Um documento específico, mas por NSU (não por chave) — não usado no projeto |

**Implicação de design**: achar um CT-e por chave de acesso é uma busca client-side —
`app/services/cte_client.py` pagina `distNSU` a partir de `ultNSU="0"`, decodifica cada `docZip`,
e compara a chave de cada documento com a procurada.

## 2. Endpoint confirmado (teste real, 21/08/2026)

| Item | Valor |
|---|---|
| URL | `https://www1.cte.fazenda.gov.br/CTeDistribuicaoDFe/CTeDistribuicaoDFe.asmx` (Ambiente Nacional) |
| Método SOAP | `cteDistDFeInteresse` |
| Namespace do wrapper WSDL | `http://www.portalfiscal.inf.br/cte/wsdl/CTeDistribuicaoDFe` |
| Elemento de dados | `cteDadosMsg` (análogo ao `nfeDadosMsg` da NF-e) |
| Namespace do `distDFeInt` | `http://www.portalfiscal.inf.br/cte` |
| Versão do schema | `1.00` |
| `cUFAutor` | `"42"` — mesmo valor usado na NF-e, aceito sem reclamação |

Todos acertados de primeira no teste real (`cStat 138`), sem precisar iterar — diferente da Fase 0
da NF-e, onde o primeiro namespace tentado estava errado.

## 3. Formato da chave dentro do documento

Não existe uma tag `<chCTe>` separada dentro do `infCte` (diferente do que se esperava por
analogia). A chave de acesso vem no atributo `Id` do elemento `<infCte>`:

```xml
<infCte Id="CTe43260830800793000275570040000013051150732250" versao="4.00">
```

Mesmo padrão do `Id="NFe" + 44 dígitos` da NF-e. `extract_ch_cte()` em `cte_client.py` extrai isso
via regex `Id="CTe(\d{44})"`.

Documentos que são **eventos** (cancelamento, EPEC etc.) vêm com `schema="procEventoCTe_v4.00.xsd"`
no atributo do `docZip` e não têm esse atributo `Id="CTe..."` — tratados como "não é o documento
procurado", não como erro.

## 4. Manifestação do tomador — ⚠️ status não 100% confirmado

O documento de teste (21/08/2026) voltou **completo** (`cteProc` com `infCte` inteiro) direto da
distribuição, sem nenhum evento de manifestação antes — e a Nota Técnica não menciona manifestação
em nenhuma das 12 páginas.

**Mas o teste tem um confundidor real**: se outro sistema (ex: programa do contador) já consultou
esse mesmo CT-e antes de nós, o `distNSU` devolveria o documento completo de qualquer forma,
exista ou não a exigência — o teste não distingue as duas hipóteses.

Busca por um schema de "resumo" tipo `resCTe` (análogo ao `resNFe_v1.01.xsd` da NF-e, que é o
sinal formal desse estado pré-manifestação) não achou nenhuma menção em fontes técnicas —
evidência indireta a favor de "não existe", mas não conclusiva.

**Decisão de implementação**: `cte_client.py` **não** tenta detectar/enviar manifestação (não há
schema conhecido pra checar, e inventar um mecanismo sem pesquisa seria pior que não ter nada).
Em vez disso, um log de aviso dispara se o documento encontrado vier suspeitosamente curto — sinal
fraco, não bloqueia o fluxo. Se isso disparar na prática algum dia, investigar com dado real em
mãos.

## 5. Achado não previsto: janela de retenção do buffer de distribuição

No teste real, `distNSU` com `ultNSU="0"` **não** retornou a partir do NSU 1 — o primeiro NSU
disponível já era 3599 (de um total `maxNSU` 4088 no momento). Hipótese mais provável: SEFAZ não
retém o buffer de distribuição indefinidamente, só uma janela recente (documentos/eventos mais
antigos somem do `distNSU`, mesmo que o `nCT`/data de emissão seja antigo).

Não é erro do cliente — o `cStat` veio de sucesso. Não afeta o caso de uso atual (só precisamos de
chaves recentes), mas explica por que paginar do zero não significa necessariamente percorrer
todo o histórico da empresa.

## 6. Volume de paginação observado

Achar uma chave de agosto/2026 levou **~9 lotes de 50** (450 NSUs) a partir do NSU mais antigo
ainda disponível. Gerenciável — não bateu no risco de "inviável percorrer do zero toda vez"
levantado antes do teste. `cte_client.py` não persiste o último NSU visto entre chamadas (cada
consulta pagina do zero) — decisão consciente de não resolver isso agora (YAGNI), documentada como
risco de performance conhecido caso o volume cresça muito no futuro.

## 7. `cStat` reaproveitados da NF-e

Mesmos códigos, mesmo significado — não achamos nenhum código específico de CT-e diferente do
padrão nacional de Distribuição DFe:

| cStat | Significado |
|---|---|
| 138 | Documento(s) localizado(s) |
| 137 | Nenhum documento localizado |
| 640 | CNPJ/CPF do interessado não possui permissão pra consultar |
| 217 | Documento inexistente para a chave informada |
| 656 | Consumo indevido (bloqueio de 1h) — mesma regra de cooldown já implementada em `rate_limiter.py`, reaproveitada sem alteração |

Cooldown de 1h confirmado **oficialmente** pro CT-e na própria Nota Técnica (não só por analogia
com a NF-e).

## 8. Referências

- [Nota Técnica 2015/002 — Web Service de Distribuição de DF-e de Interesse dos Atores do CT-e, CT-e OS e GTV-e](https://www.cte.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=5c1PwLTdrCA%3D)
- [Portal do CT-e — Web Services](https://www.cte.fazenda.gov.br/portal/webServices.aspx)
- `TODOCTE.md` — raciocínio completo, incluindo os achados descartados (ex: hipótese SVRS errada) e os testes reais passo a passo
- [`protocolo-sefaz.md`](protocolo-sefaz.md) — equivalente pra NF-e, várias regras (cooldown, `cStat`) compartilhadas