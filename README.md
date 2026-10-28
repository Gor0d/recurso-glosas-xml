# XML-CAPS — Recurso de Glosa TISS (CAPESESP / Soul MV)

Investigação e primeira peça do fluxo de glosa/recurso do convênio CAPESESP no Soul MV
(hospital usuário do MV). O relatório completo de investigação Oracle + parecer de
viabilidade é mantido fora deste repositório (uso interno).

**Pode existir um projeto de diagnóstico anterior mais completo** no seu ambiente, com
roteiro de execução em PRD (script de preparação com guarda de rollback) e matriz de
homologação. Ele pode já ter identificado, por exemplo, que o convênio está com
`SN_IMPORTA_GLOSA_RECEB = N` e que o(a) usuário(a)-piloto não tem o papel `159/FFAG` —
isso é mais preciso do que "módulo licenciado ou não" e deveria ser o ponto de partida de
qualquer ação de habilitação. Leia esse diagnóstico local antes de continuar a parte de
habilitação nativa.

**Fonte de dados do MV**: só o MCP `soul-mv-erp` (ou um projeto equivalente que exponha
`tools/soul_mv.py`) tem autorização/configuração de conexão com o Oracle. Este repo tem
`.codex/config.toml` habilitando o MCP `soul-mv-erp` também para o Codex, somente leitura
(a função `executar_sql_livre` só aceita `SELECT`). Nenhum script deste repositório deve abrir
uma conexão Oracle própria — `scripts/reconcile_glosa.py` mostra o padrão certo
(`ErpMcpServerGateway` importa `tools.soul_mv` do projeto MCP em vez de duplicar
credenciais).

## Estrutura

- `data/oracle_dump/` — dumps somente-leitura (sem PII de paciente) exportados do Oracle
  via `mcp__soul-mv-erp__executar_sql_livre` para um caso-piloto anonimizado. Servem de
  fixture reprodutível sem precisar de credencial de banco. **Este diretório não é
  versionado neste repositório público** — veja `.gitignore`.
- `scripts/reconcile_glosa.py` — lê o XML `DEMONSTRATIVO_ANALISE_CONTA` da CAPE (fora do
  repo, ver `--xml`) e cruza cada `sequencialItem` contra `DBAMV.TISS_ITGUIA` (procedimentos,
  tabela TISS 22) e `DBAMV.TISS_ITGUIA_OUT` (materiais/medicamentos/outras despesas, tabelas
  19/20/00/18...). Gera `output/glosa_reconciliation.json`. **Não escreve no MV.**
- `output/glosa_reconciliation.json` — contrato de saída, é o que o Codex deve consumir.
- `scripts/recurso_glosa.py` — cria o JSON de decisões, valida as regras CAPESESP, gera o
  XML ISO-8859-1 e registra separadamente o upload manual.
- `scripts/analyst_panel.py` + `web/panel.html` — painel local do analista; não transmite
  dados e reutiliza o mesmo gerador/validador da CLI.
- `tests/` — testes das regras financeiras, confirmação humana, hash, encoding e XSD.

## Como rodar

```
python scripts/reconcile_glosa.py --xml "C:\caminho\para\o\demonstrativo.xml"
```

O XML original (tem `numeroCarteira`/`senha` do beneficiário) fica fora do repo de propósito
— não versionar. O script só grava dados técnicos no `output/`, que também não é versionado.

### Painel do analista

```
python scripts/analyst_panel.py --xsd "C:\caminho\tissV4_01_00.xsd"
```

Abra `http://127.0.0.1:8766` (ajuste a porta com `--port` se precisar). O painel carrega o contrato, permite classificar todos os
itens e salva `output/decisoes_recurso.json`. Os números de guia são apenas sugestões: a
caixa de confirmação J/K deve ser marcada pelo analista depois da conferência no
Demonstrativo de Análise de Conta. Sem `--xsd`, o painel ainda gera o XML, mas mostra um
aviso explícito de que a validação formal não foi executada.

O painel foi reorganizado como **Nexo Glosas**, uma central operacional com cinco áreas:

- visão geral do protocolo, valores, pendências e principais códigos de glosa;
- análise item a item, com os bloqueios de segurança já existentes;
- dicionário operacional dos códigos presentes no piloto, com descrição do catálogo MV,
  características, conferências, documentos sugeridos e texto-base para revisão humana;
- catálogo prioritário com 64 códigos dos grupos de honorários, OPME, diárias e taxas,
  incluindo filtro por linha de negócio e classificação na exportação para BI;
- montagem e checklist do recurso antes da geração do XML;
- indicadores e exportação CSV para Power BI/Excel em `/api/export/bi.csv`;
- integrações, deixando explícito se a fonte é arquivo TISS ou snapshot MV e que não há
  escrita automática no Oracle.

O fluxo continua local-first e não envia o recurso automaticamente. O download do último
XML gerado fica disponível em `/api/download/xml`.

### Docker

```powershell
docker compose up -d --build
```

O serviço fica disponível em `http://localhost:8877`. A pasta `output/` é montada como
volume para preservar decisões, XMLs e exportações entre recriações do contêiner.

No primeiro acesso, o sistema solicita a criação do administrador; não existe senha padrão.
Depois, use **Acessos** para criar contas individuais de analista para a equipe. As
senhas são derivadas localmente e as sessões expiram em 12 horas. O banco de autenticação
`output/nexo_auth.sqlite3` fica no volume e é excluído do contexto de build e do Git.

A tela **Checklist MVP** separa o piloto em quatro blocos: acesso, dados/conciliação,
recurso TISS e integração MV. As verificações técnicas são automáticas; conferências humanas
registram o nome do usuário que as confirmou. Os controles da integração MV só devem ser
marcados depois de conexão em HML, aprovação do DE/PARA e teste de rollback. O painel não
executa escrita automática no Oracle.

### CLI e validação XSD

```
python scripts/recurso_glosa.py template
python scripts/recurso_glosa.py generate --xsd "C:\caminho\tissV4_01_00.xsd"
python -m unittest discover -s tests -v
```

`generate` é sempre local/dry-run. Para registrar que o upload foi realmente concluído no
Portal Protheus e bloquear outro recurso para o protocolo:

```
python scripts/recurso_glosa.py mark-sent --protocol 00000001 --xml output\recurso_glosa.xml --confirm-uploaded
```

Esse comando não envia o XML. O registro fica em `output/submission_registry.sqlite3`.
Não o execute antes da confirmação do upload pelo operador.

## Resultado no caso-piloto (identificadores anonimizados: protocolo 00000001, guia 100000)

123 itens no total: **92 CONFIRMADO** (mesmo `SQ_ITEM`, mesmo código de procedimento, mesmo
valor), **31 PROVÁVEL**, **0 NÃO LOCALIZADO**.

**Achado importante dos 31 PROVÁVEL**: não é só "recodificação de tabela própria" como a
hipótese inicial supunha. Em pelo menos alguns casos (ex.: `sequencialItem` 0104: o XML da
CAPE traz "SANRO LIS" — luva cirúrgica — e o Oracle tem "SONDA ASPIR TRAQUEAL 14" no mesmo
`SQ_ITEM`/mesma data, com o valor batendo por coincidência em R$28,00) a correspondência por
valor é uma coincidência, não um match real. **Antes de usar esses 31 itens para gerar
qualquer recurso, um analista precisa confirmar manualmente a descrição do item** — o script
sinaliza isso no campo `motivo` de cada item PROVÁVEL, não assume que está certo.

## Validação XSD

`xsd/tiss_v4_03_00/` tem o schema oficial da ANS baixado de
[gov.br/ans](https://www.gov.br/ans/pt-br/assuntos/prestadores/padrao-para-troca-de-informacao-de-saude-suplementar-2013-tiss)
(pacote "Componente de Comunicação", versão vigente 4.03.00). **Ressalva de versão**: o XML
da CAPE declara `Padrao=4.01.00` no cabeçalho; a ANS só disponibiliza pra download a versão
vigente do schema (4.03.00 em set/2026), não o arquivo arquivado de 4.01.00. Validei o XML de
recurso gerado por `recurso_glosa.py` contra esse schema 4.03.00 e passou limpo — mas isso não
é garantia formal de conformidade com 4.01.00 especificamente, é a melhor aproximação
disponível. `scripts/recurso_glosa.py generate` e `scripts/analyst_panel.py` já usam esse XSD
como padrão (não precisa mais passar `--xsd` manualmente).

## Papéis

- **Claude Code**: investigação Oracle contínua, os dumps/scripts, resolver os pontos em
  aberto do DE/PARA.
- **Codex**: consome `output/glosa_reconciliation.json` (e tem MCP `soul-mv-erp` somente
  leitura disponível via `.codex/config.toml`) para construir o gerador de XML de
  `RECURSO_GLOSA` (layout no manual da CAPESESP) e o painel do analista. Handoff completo,
  incluindo o diagnóstico do projeto-base, em `docs/CODEX_HANDOFF.md`.
