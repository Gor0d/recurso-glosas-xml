# Mapeamento: cadastro de glosa → vínculo → recurso → XML de envio (nativo MV)

Documento de referência técnica, não um guia de uso. Todo achado abaixo vem de consulta
SELECT ao Oracle de produção (schema DBAMV/DBASGU/DBAPS) nas sessões de 2026-09-08 a
2026-10-06. Marcação usada: **CONFIRMADO** (validado via dado real ou código-fonte),
**PROVÁVEL** (inferido, não testado na tela), **A TESTAR** (só dá pra saber testando a
tela de verdade, logado como usuário real — não DBAMV).

## Achado central desta revisão: dois mecanismos nativos, não um

Até 2026-09-29 eu tinha mapeado um único caminho (o caminho "TISS"): tabelas
`TISS_RETORNO_DEMON_CONTA*`, `motivo_recurso_glosa`, `justifica_recurso_glosa`,
`convenio_conf_tiss_glosa`. Foi nesse caminho que a habilitação de 02-05/10 trabalhou
(convênio liberado, papel FFAG, motivo/justificativa cadastrados).

Em 06/10, testando a tela real ("Entrega de Recurso de Glosa", menu **Financeiro** →
Auditoria e Controle de Recursos de Glosas → Lançamentos → Entrega de Recurso de Glosas),
descobri que ela **não usa nenhuma dessas tabelas**. O pacote por trás dela
(`DBAMV.PKG_FFAG_M_ENTREGA_GLOSA`) grava em `REMESSA_FATURA` (apelidada `REM_FAT` no
código) e `MOV_GLOSAS`, ligado a `CON_REC` (um mecanismo financeiro mais antigo, usado
também para outras coisas além de glosa TISS).

Ou seja: **existem dois caminhos nativos, e não sabemos ainda se eles se conectam em
algum ponto, ou se são dois sistemas paralelos que resolvem problemas parecidos de
formas diferentes.** Isso precisa ser resolvido antes de qualquer automação.

---

## Caminho A — "TISS" (tabelas que habilitamos, XML-driven)

```
XML DEMONSTRATIVO_ANALISE_CONTA (retorno da CAPE)
  ↓ [import — mecanismo real NÃO localizado, ver nota]
TISS_MENSAGEM
  ↓ ID_PAI
TISS_RETORNO_DEMON_CONTA        (cabeçalho da fatura/demonstrativo)
  ↓ ID_PAI
TISS_RETORNO_DEMON_CONTA_GUIA   (guia: NR_GUIA, CD_ATENDIMENTO, CD_REG_FAT)
  ↓ ID_PAI
TISS_RETORNO_DEMON_CONTA_PROC   (item: SQ_ITEM = sequencialItem do XML) [CONFIRMADO: gatilhos TRG_TISS_RD_CTAP_GRAVA_PROC/2 disparam aqui]
  ↓ ID_PAI
TISS_RETORNO_DEMON_CONTA_PRC_G  (motivo + valor da glosa do item)
```

**Status**: cadeia de tabelas 100% mapeada e confirmada (constraints/colunas reais). Mas
**nenhum pacote PL/SQL faz INSERT em `TISS_RETORNO_DEMON_CONTA`** — busquei em todo o
`ALL_SOURCE` do schema DBAMV e não achei. A importação real do XML provavelmente
acontece na camada Java/HTML5 do MV, fora do banco — **ainda não localizei a tela que
faz essa importação** (não é nenhuma das que exploramos até agora).

**Parametrização feita (02-05/10, confirmada ainda válida em 06/10)**:
- `dbamv.convenio.SN_IMPORTA_GLOSA_RECEB = 'S'` pro convênio 20 (CAPE).
- `dbamv.motivo_recurso_glosa` / `justifica_recurso_glosa`: 1 linha piloto cada (texto
  provisório "fase piloto de homologação").
- `dbamv.convenio_conf_tiss_glosa`: **continua com 0 linhas pra CAPE** — o DE/PARA
  TISS↔motivo MV nunca foi preenchido.
- Papel 159 (FFAG) com 7 módulos ligados: `M_REGISTRO_RECURSO_GLOSA`,
  `M_MOT_RECURSO_GLOSA`, `M_JUSTIFICA_REC_GLOSA`, `M_ENTREGA_RECURSO`,
  `M_RECEBE_RECURSO`, `R_SINTE_RECURSO`, `R_ANALI_RECUR_GLOSA`.

**Pendência crítica**: não achamos a tela que usa esses 7 módulos. Nenhum deles bateu
com a tela real que encontramos (`M_ENTREGA_GLOSA`, que não é `M_ENTREGA_RECURSO`). É
possível que essas 7 permissões sirvam pra telas que ninguém testou ainda, ou que o nome
"Registro de Recurso de Glosas" da investigação de 25/08 estivesse errado desde o início.

---

## Caminho B — "Financeiro/REMESSA_FATURA" (tela que testamos de verdade em 06/10)

```
REMESSA_FATURA (CD_REMESSA — confirmado: guia 100000 → CD_REMESSA 90001)
  ↓ tela "Entrega de Recurso de Glosa" (menu Financeiro, módulo M_ENTREGA_GLOSA)
  ↓ pacote DBAMV.PKG_FFAG_M_ENTREGA_GLOSA
       P_I_WVI_RF_CD_REMESSA              (valida remessa digitada)
       P_I_WVI_RF_VL_GLOSA_NAO_IDEN       (valida valor de glosa não identificada)
       P_I_WVI_RF_DT_ENTREGA_DA_FAT       (valida data de entrega da fatura)
       F_GERA_REGISTRO_CON_REC            (gera registro em CON_REC)
       P_GRAVA_RAT_CON_REC                (grava rateio do CON_REC)
       P_GERA_REGISTRO_MOV_GLOSAS         (INSERT em MOV_GLOSAS)
       F_ACEITE_DE_GLOSA                  (aceite de glosa)
  ↓
MOV_GLOSAS (CD_REMESSA, CD_RECCON_REC, VL_MOVIMENTACAO, DS_MOV_GLOSA, TP_STATUS)
CON_REC    (controle de recebimento — mecanismo financeiro genérico, não exclusivo de TISS)
```

**Status**: este é o caminho que a tela real usa, confirmado pelo código-fonte e pelo
print da sessão de 06/10. `MOV_GLOSAS` pra remessa 90001 = 0 linhas (nada lançado ainda,
esperado). A tela em si é baseada em **entrada manual de valor de glosa por remessa**,
não em importação estruturada item a item do XML.

**Ponto de atenção forte**: os botões da tela são "Conf. Entrega da Glosa", "Canc. a
Operação", "Informar nova Remessa", "**Imprimir** Reapres. de Glosas" — o último sugere
**impressão de relatório físico**, não geração de XML digital. **Não vi, no pacote
`PKG_FFAG_M_ENTREGA_GLOSA`, nenhuma função de geração de XML** (nada como
`F_GERA_XML`/`P_EXPORTA_XML`). Isso é um sinal de que esse caminho pode ser só o
registro financeiro da glosa — a geração do XML de recurso pode estar em outro módulo
ainda não localizado, ou pode nem existir nativamente pra esse fluxo específico.

**Outros módulos reais vistos no menu (06/10), ainda não habilitados pro papel 159**
(todos `N/N/N` hoje):

| Módulo (confirmado no banco) | Tela no menu | Pacote provável |
|---|---|---|
| `M_ENTREGA_GLOSA` | Entrega de Recurso de Glosas | `PKG_FFAG_M_ENTREGA_GLOSA` (confirmado) |
| `M_CANCELA_GLOSA` | Cancelamento de Recurso de Glosas | `PKG_FFAG_M_CANCELA_GLOSA` (nome provável, não lido) |
| `M_RECEBE_GLOSA` | Recebimento de Recurso de Glosas | `PKG_FFAG_M_RECEBE_GLOSA` (nome provável, não lido) |
| `M_GLOSAS_RETRO` | Recurso de Glosas Retroativas | não lido |
| `M_RECEBE_GLOSA_RETRO` | Recebimento de Recursos de Glosas Retroativas | não lido |
| `M_ACEITE_GLOSA` | Aceite de Glosa | `PKG_FNCP_M_ACEITE_GLOSA` (confirmado no grep) |
| `M_AUDITORIA_AMB` / `M_AUDITORIA_CONTA_HOSP` | Auditoria Conta Ambulatorial/Hospitalar | não lido |
| `M_GLOSA_GERENCIAL`, `M_GLOSA_GRU_PRO`, `M_GLOSA_GRU_FAT` | relatórios de glosa (Glosa Gerencial, por Grupo de Procedimento/Faturamento) | não lido |

---

## O que falta descobrir (nesta ordem, cada um destrava o próximo)

1. **Testar a tela "Entrega de Recurso de Glosa" com dado real**, logado como Paula ou
   Joyce (não DBAMV — o DBAMV ignora toda permissão, não prova nada). Usar remessa
   `90001`. Ver se ela consegue digitar/salvar algo, e o que acontece.
2. **Se salvar**, conferir se cai em `MOV_GLOSAS`/`CON_REC` como o código sugere — eu
   confirmo isso via SELECT na hora.
3. **Achar onde o XML de recurso é gerado de verdade.** Ainda não achamos. Pode estar
   atrás de um módulo que ainda não testamos (`M_GLOSA_GERENCIAL`? um módulo fora da
   lista de "glosa/recurso" que nunca buscamos?), ou pode ser que esse MV não tenha
   gerador nativo de XML pra esse fluxo específico — nesse caso o gerador do XML-CAPS
   (`recurso_glosa.py`) deixa de ser só apoio e vira o caminho principal.
4. **Achar a tela de importação do XML `DEMONSTRATIVO_ANALISE_CONTA`.** Continua não
   localizada. Sem ela, o cadastro "automático" da glosa a partir do XML não existe
   nativamente — hoje só existe via `reconcile_glosa.py` (que cruza, não grava).
5. **Decidir o DE/PARA `convenio_conf_tiss_glosa`** — só faz sentido depois de saber se
   o Caminho A é mesmo o que vale a pena perseguir.

## Recomendação neste ponto

Não dá pra prometer um "cadastro automático nativo" até resolver os itens 1-4. Dois
caminhos possíveis a partir daqui:

- **Via nativa (Caminho B)**: testar a tela real com a Paula/Joyce, descobrir até onde
  ela vai sozinha, e se faltar geração de XML, ver se existe outra tela/relatório
  específico pra isso (teria que vasculhar o menu "Consultas" que aparece no print,
  ainda não expandido).
- **Via complementar (XML-CAPS)**: assumir que a geração de XML nativa pode não existir
  pra esse fluxo, e que `recurso_glosa.py` é o gerador real — nesse caso o "cadastro da
  glosa no MV" vira só a entrada manual pela tela de Entrega de Recurso de Glosa (pra
  efeito financeiro/contábil), separada da geração do XML (que sai do XML-CAPS).

Essas duas rotas não são excludentes, mas precisam ser testadas na tela antes de
qualquer automação — construir automação em cima de um caminho que ainda não foi visto
funcionando na prática é arriscado.
