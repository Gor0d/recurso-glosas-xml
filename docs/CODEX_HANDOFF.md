# Handoff para o Codex — Gerador de XML de Recurso de Glosa (CAPESESP / Soul MV)

Você (Codex) está entrando neste repositório sem ter visto a investigação que já foi feita.
Este documento é autocontido. **Leia também, antes de codar, os arquivos do projeto-base**
listados na seção 0 — este handoff resume o essencial, mas o projeto-base tem o diagnóstico
completo e é a fonte de verdade sobre o estado do MV.

## 0. Projeto-base (leia primeiro)

Este trabalho **não parte do zero**. Existe um projeto de diagnóstico e planejamento mais
completo, feito em 2026-08-25, em:

```
C:\Users\emers\Projetos\Recurso de Glosas\
```

Arquivos relevantes lá:
- `Projeto_Recurso_de_Glosa.html` — diagnóstico completo, decisão executiva, rota de
  implantação (HML → homologação → PRD), matriz de 25 cenários de teste, riscos, plano de
  treinamento, minuta de resposta à coordenadora do setor.
- `Implantacao_Recurso_Glosa_PRD.sql` — script de preparação em PRD, **já com guarda de
  segurança** (`c_aplicar = FALSE` por padrão, roda em modo simulação com `ROLLBACK`). Mostra
  exatamente quais tabelas MV entram em jogo: `dbamv.motivo_recurso_glosa`,
  `dbamv.justifica_recurso_glosa`, `dbamv.convenio_conf_tiss_glosa`, `dbasgu.papel_usuarios`.
- `diagnostico_mcp_readonly.py` / `diagnostico_viabilidade_banco.py` — scripts de diagnóstico
  somente-leitura, ambos importando `tools.soul_mv` de `erp-mcp-server` (ver seção 1).
- `.codex/config.toml` — mesmo arquivo que foi copiado para este repo (`XML-CAPS/.codex/`).

**Conclusão de negócio desse projeto (confirmada de novo nesta sessão via MCP, 2026-09-08):**
não é falta de licença/módulo. O módulo já está implantado (49 tabelas, 58 packages, 20
views, 10 triggers de glosa/recurso, todos `VALID`) e o MV já usou a parte de glosa em geral
(6.275 glosas, 318.634 movimentos, 37 remessas historicamente). O que falta é:

1. **`dbamv.convenio.SN_IMPORTA_GLOSA_RECEB = 'N'`** para o convênio CAPE SAÚDE
   (`cd_convenio = 20`) — flag que bloqueia a importação de glosa desse convênio.
2. **`dbamv.convenio_conf_tiss_glosa`** (DE/PARA `cd_glosa_tiss` ↔ `cd_motivo_glosa`) só tem
   1 linha cadastrada (Unimed Belém) — nenhuma para a CAPE.
3. A primeira usuária-piloto tem 2 logins ativos mas **não tem o papel `159/FFAG`**
   concedido — é isso que bloqueia o acesso às telas nativas.
4. `dbamv.motivo_recurso_glosa` / `dbamv.justifica_recurso_glosa` estão vazias — motivo e
   justificativa de recurso ainda não foram cadastrados.

Telas nativas reais do MV (path de menu): **Faturamento → Auditoria e Controle de Recursos de
Glosas → Lançamentos → Registro de Recurso de Glosas** (e também: Motivo de Recurso,
Justificativa de Recurso, Gerenciar Recursos Glosa, Importar XML Recursos, Relatório TISS
Recurso V4).

Ou seja: a rota mais rápida de valor real é **habilitação nativa** (parametrizar os 4 pontos
acima em HML, testar, promover a PRD) — isso é trabalho de TI/DBA no MV, fora do escopo de
código deste repositório. **O seu trabalho aqui (gerador de XML + painel) é a camada
complementar** para o hospital não ficar bloqueado enquanto a habilitação nativa não sai, e
também serve de validador independente depois.

## 1. Acesso ao Oracle/MV — o que você TEM e o que NÃO PODE fazer

Este repositório tem `.codex/config.toml` configurado (mesmo padrão do projeto-base) apontando
para o MCP `soul-mv-erp`, que roda a partir de `C:\Users\emers\Projetos\erp-mcp-server`. Ou
seja, **você tem acesso de leitura ao Oracle do MV via MCP**, igual ao Claude Code nesta sessão.

Regras que não têm exceção:
- **Só SELECT.** A função `executar_sql_livre` do MCP já rejeita qualquer coisa que não comece
  com `SELECT` — não tente contornar isso.
- **Nunca** crie um cliente Oracle novo (`oracledb`/`cx_Oracle` com DSN/usuário/senha
  inventados, hardcoded, ou em `.env` novo). As únicas fontes autorizadas de dado real do MV
  são: (a) o MCP `soul-mv-erp` (interativo, disponível pra você agora), ou (b) reusar
  `C:\Users\emers\Projetos\erp-mcp-server\tools\soul_mv.py` em scripts Python — é o padrão que
  `scripts/reconcile_glosa.py` deste repo já usa (classe `ErpMcpServerGateway`) e que o
  projeto-base usa em `diagnostico_mcp_readonly.py`.
- **Nunca** faça INSERT/UPDATE/DELETE/DDL, mesmo que o MCP permitisse (não permite). Se algum
  dia esse trabalho evoluir para escrever no MV (ex.: aplicar o `Implantacao_Recurso_Glosa_PRD.sql`
  de verdade), isso é decisão humana, feita manualmente pelo usuário/DBA — nunca automatize.
- **Dados sensíveis**: se rodar consultas que trazem nome de paciente, CPF, cartão de
  beneficiário, senha de autorização, etc., não grave isso em arquivo neste repo nem em log.
  Os dumps já existentes em `data/oracle_dump/` foram deliberadamente exportados sem esses
  campos.

## 2. Contexto do negócio

O hospital (Beneficente Portuguesa) recebe da operadora **CAPE SAÚDE/CAPESESP** (registro ANS
324477, convênio MV `cd_convenio = 20`) arquivos XML TISS `DEMONSTRATIVO_ANALISE_CONTA` — o
retorno que diz quanto foi faturado, processado, liberado e glosado por item de cada guia.
Hoje isso é tratado manualmente. O objetivo do projeto é: importar esse XML → identificar as
glosas → deixar um analista decidir (recorrer / aceitar / aguardar documentação) → gerar o XML
de **recurso de glosa** no formato exigido pela CAPESESP → mandar pro Portal Protheus da
operadora.

## 3. O que já existe neste repositório (XML-CAPS)

```
XML-CAPS/
├── README.md
├── .codex/config.toml                 — MCP soul-mv-erp habilitado pra você
├── data/oracle_dump/                  — dumps somente-leitura do Oracle (sem PII de paciente)
├── scripts/reconcile_glosa.py         — parseia o XML da CAPE + cruza com o Oracle
└── output/glosa_reconciliation.json   — CONTRATO: é isso que você consome
```

Caso real usado como piloto: protocolo `00000001`, lote `9001`, guia `100000`. Rode
`python scripts/reconcile_glosa.py --xml <caminho do XML>` para regerar o contrato (o XML
original tem dado de beneficiário, por isso não está versionado — está em
`C:\Users\emers\Downloads\XML CAPS\`).

### 3.1 Formato do `glosa_reconciliation.json` (contrato de entrada)

```json
{
  "protocolo": {
    "numero_lote_prestador": "9001",
    "numero_protocolo": "00000001",
    "numero_guia_prestador": "100000"
  },
  "resumo": {"total_itens": 123, "CONFIRMADO": 92, "PROVAVEL": 31, "NAO_LOCALIZADO": 0},
  "itens": [
    {
      "sequencialItem": 23,
      "status": "CONFIRMADO",
      "motivo": "codigoProcedimento e valor batem exatamente.",
      "xml": {
        "sequencial_item": 23,
        "data_realizacao": "2026-05-11",
        "codigo_tabela": "19",
        "codigo_procedimento": "70222797",
        "valor_informado": 62.04,
        "valor_glosa": 62.04,
        "tipo_glosa": "2012"
      },
      "oracle": {
        "sq_item": 23,
        "tp_tab_fat": "19",
        "cd_procedimento": "70222797",
        "vl_total": 62.04,
        "dt_realizado": "2026-05-11",
        "origem_tabela": "TISS_ITGUIA_OUT"
      }
    }
  ]
}
```

- `status` é `CONFIRMADO`, `PROVAVEL` ou `NAO_LOCALIZADO`.
- **Regra crítica**: itens `PROVAVEL` **não** podem entrar num recurso automaticamente. Na
  prática já vimos casos onde o match por valor é coincidência (ex.: `sequencialItem` 0104 —
  luva cirúrgica no XML vs sonda de aspiração no Oracle, ambos R$28,00 na mesma data). Um
  humano precisa confirmar a descrição antes de incluir um item `PROVAVEL` num recurso.

## 4. O que você precisa construir

### 4.1 Gerador do XML `RECURSO_GLOSA`

Um módulo/CLI que recebe: (a) o `glosa_reconciliation.json`, e (b) as decisões do analista
por item (`RECORRER` / `ACEITAR_GLOSA` / `AGUARDAR_DOCUMENTACAO` + justificativa por item
recorrido), e produz um XML TISS válido no **layout específico exigido pela CAPESESP**
(confirmado no manual oficial da operadora, `manual_recurso_glosa_eletronico_06_2023.pdf`, em
`C:\Users\emers\Downloads\XML CAPS\` — vale ler o PDF, mas o essencial já está transcrito
abaixo).

**Template real do manual da CAPESESP** (mantenha a estrutura/nomes de tag exatamente assim —
não é um exemplo genérico de TISS, é o formato específico que a CAPESESP valida):

```xml
<?xml version="1.0" encoding="ISO-8859-1"?>
<ans:mensagemTISS xmlns:ans="http://www.ans.gov.br/padroes/tiss/schemas" xmlns="http://www.w3.org/2001/XMLSchema">
  <ans:cabecalho>
    <ans:identificacaoTransacao>
      <ans:tipoTransacao>RECURSO_GLOSA</ans:tipoTransacao>
      <ans:sequencialTransacao>32603</ans:sequencialTransacao>
      <ans:dataRegistroTransacao>2022-06-01</ans:dataRegistroTransacao>
      <ans:horaRegistroTransacao>09:33:20</ans:horaRegistroTransacao>
    </ans:identificacaoTransacao>
    <ans:origem>
      <ans:identificacaoPrestador>
        <ans:CNPJ>00000000000100</ans:CNPJ>
      </ans:identificacaoPrestador>
    </ans:origem>
    <ans:destino>
      <ans:registroANS>324477</ans:registroANS>
    </ans:destino>
    <ans:Padrao>4.01.00</ans:Padrao>
  </ans:cabecalho>
  <ans:prestadorParaOperadora>
    <ans:recursoGlosa>
      <ans:guiaRecursoGlosa>
        <ans:registroANS>324477</ans:registroANS>
        <ans:numeroGuiaRecGlosaPrestador>1234567</ans:numeroGuiaRecGlosaPrestador>
        <ans:nomeOperadora>CAPESESP-CAIXA DE PREV. E ASSIST. DOS SERV. DA FUND. NAC. DE SAUDE</ans:nomeOperadora>
        <ans:objetoRecurso>2</ans:objetoRecurso>
        <ans:numeroGuiaRecGlosaOperadora>1234567</ans:numeroGuiaRecGlosaOperadora>
        <ans:dadosContratado>
          <ans:cnpjContratado>00000000000100</ans:cnpjContratado>
        </ans:dadosContratado>
        <ans:numeroLote>123456</ans:numeroLote>
        <ans:numeroProtocolo>01026641</ans:numeroProtocolo>
        <ans:opcaoRecurso>
          <ans:recursoGuia>
            <ans:numeroGuiaOrigem>00000001</ans:numeroGuiaOrigem>
            <ans:numeroGuiaOperadora>1234567</ans:numeroGuiaOperadora>
            <ans:opcaoRecursoGuia>
              <ans:itensGuia>
                <ans:sequencialItem>0044</ans:sequencialItem>
                <ans:dataInicio>2022-01-19</ans:dataInicio>
                <ans:procRecurso>
                  <ans:codigoTabela>19</ans:codigoTabela>
                  <ans:codigoProcedimento>78244960</ans:codigoProcedimento>
                  <ans:descricaoProcedimento>Lanceta seg. desc.28ga 0,36X1,8mm C/100unid.</ans:descricaoProcedimento>
                </ans:procRecurso>
                <ans:codGlosaItem>1705</ans:codGlosaItem>
                <ans:valorRecursado>5.04</ans:valorRecursado>
                <ans:justificativaItem>SIMPRO 0000164731 LANCETA SF 200UNID. ABOTT.R$ 4,500 + 12% 5,04</ans:justificativaItem>
              </ans:itensGuia>
            </ans:opcaoRecursoGuia>
          </ans:recursoGuia>
        </ans:opcaoRecurso>
        <ans:valorTotalRecursado>5.04</ans:valorTotalRecursado>
        <ans:dataRecurso>2022-06-01</ans:dataRecurso>
      </ans:guiaRecursoGlosa>
    </ans:recursoGlosa>
  </ans:prestadorParaOperadora>
  <ans:epilogo>
    <ans:hash>40024bd02634144c65b92d898361c93a</ans:hash>
  </ans:epilogo>
</ans:mensagemTISS>
```

DE/PARA do `glosa_reconciliation.json` para as tags do recurso (uma `<ans:itensGuia>` por
item que o analista marcou `RECORRER`):

| Tag do XML de recurso | Vem de |
|---|---|
| `numeroGuiaRecGlosaPrestador` / `numeroGuiaRecGlosaOperadora` | Coluna "J" do demonstrativo original — **não está no contrato atual**; se precisar, peça pro Claude Code ajustar `reconcile_glosa.py` (não invente o valor) |
| `numeroProtocolo` | `protocolo.numero_protocolo` — **sempre com zero à esquerda** |
| `numeroGuiaOrigem` | `protocolo.numero_guia_prestador` |
| `sequencialItem` | `itens[i].sequencialItem` (zero-padded 4 dígitos, ex. `0023`) |
| `dataInicio` | `itens[i].xml.data_realizacao` |
| `codigoTabela` / `codigoProcedimento` / `descricaoProcedimento` | `itens[i].xml.codigo_tabela` / `codigo_procedimento` — **não pode ser alterado** em relação ao original |
| `codGlosaItem` | `itens[i].xml.tipo_glosa` |
| `valorRecursado` | valor decidido pelo analista (≤ `xml.valor_glosa`) |
| `justificativaItem` | texto do analista |
| `numeroLote` | gerado por você, **não pode repetir** `protocolo.numero_lote_prestador` ("9001") |

Se quiser cruzar `codGlosaItem`/motivo com a nomenclatura MV (não obrigatório para gerar o
XML, mas ajuda o analista a entender o motivo), o catálogo relevante no Oracle é
`dbamv.glosas_tiss` (código/descrição TUSS) e `dbamv.motivo_glosa` (motivo interno MV) — ambos
consultáveis via MCP.

### 4.2 Regras de negócio obrigatórias (do manual da CAPESESP)

1. **Só é permitido 1 (um) recurso por protocolo (PEG).** Impedir gerar duas vezes para o
   mesmo `numeroProtocolo`.
2. **O código do procedimento/item recursado não pode mudar** em relação à fatura original.
3. `justificativaItem`: **máximo 150 caracteres**, cada caractere especial conta como dois — se
   ficar em dúvida na contagem exata, trunque com folga e logue um aviso em vez de gerar XML
   inválido.
4. `numeroLote` do recurso tem que ser diferente do lote original.
5. `valorRecursado` de cada item não pode ultrapassar o `valorGlosa` original daquele item.
6. `valorTotalRecursado` = soma dos `valorRecursado` de todos os itens do recurso.
7. Encoding **ISO-8859-1** (não UTF-8).
8. **Não incluir itens `NAO_LOCALIZADO`** no recurso.
9. **Itens `PROVAVEL` só entram se um humano confirmou manualmente** — exija flag explícita de
   confirmação por item `PROVAVEL`, nunca inclua por padrão.

### 4.3 Modo DRY RUN

Sempre gere o XML em modo dry-run: roda todas as validações, produz o arquivo, mas não
implementa envio automatizado. A submissão real hoje é manual, via Portal Protheus da
CAPESESP — fora do escopo de código deste repositório.

### 4.4 Painel do analista

Tela simples que lê `glosa_reconciliation.json`, deixa marcar `RECORRER` /`ACEITAR_GLOSA` /
`AGUARDAR_DOCUMENTACAO` por item com justificativa (valida os 150 caracteres em tempo real),
exige confirmação explícita pra itens `PROVAVEL`, e exporta `decisoes_recurso.json` que o
gerador do item 4.1 consome. Não precisa ler/escrever no Oracle além de consultas de apoio
(catálogo de motivo, se quiser) — tudo via MCP, somente leitura.

## 5. Critério de pronto

- Rodar o gerador contra o caso real (protocolo 00000001, guia 100000) com um
  `decisoes_recurso.json` de teste (alguns itens `CONFIRMADO` marcados `RECORRER`) e produzir
  um XML que segue a estrutura da seção 4.1, respeita as regras da 4.2, roda em dry-run.
- Nenhum código deste projeto deve criar conexão Oracle própria — só MCP ou
  `erp-mcp-server/tools/soul_mv.py`.
- Antes de declarar qualquer coisa sobre "viabilidade" ou "o que falta no MV", checar contra a
  seção 0 deste documento e os arquivos do projeto-base — não reabrir uma investigação do zero.
