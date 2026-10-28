/*
  SOUL MV / DBAMV - TESTE DE IMPORTACAO DE RETORNO XML (DEMONSTRATIVO_ANALISE_CONTA)
  AMBIENTE: HOMOLOGACAO (ORASML/sml)

  Estado entregue: SOMENTE SIMULACAO COM ROLLBACK. Nao existe modo de aplicacao neste
  script porque os dados aqui sao FABRICADOS para teste - nunca devem permanecer gravados,
  nem em HML.

  OBJETIVO
  Descobrir se a cadeia de tabelas nativas do demonstrativo aceita e reflete corretamente
  um retorno de exemplo (baseado no caso real: protocolo 00000001, lote 9001, guia 100000,
  convenio CAPE SAUDE cd_convenio=20), SEM depender da camada Java do MV (que nao foi
  localizada como pacote PL/SQL chamavel - ver observacao abaixo).

  CADEIA TESTADA (confirmada via ALL_CONSTRAINTS/ALL_TAB_COLUMNS em PRD, 2026-09-29,
  SELECT-only - AINDA NAO CONFIRMADA em HML, ver passo 0 abaixo):
    TISS_MENSAGEM (envelope)
      -> TISS_RETORNO_DEMON_CONTA.ID_PAI          (cabecalho do demonstrativo/fatura)
        -> TISS_RETORNO_DEMON_CONTA_GUIA.ID_PAI   (guia: NR_GUIA, CD_ATENDIMENTO, CD_REG_FAT...)
          -> TISS_RETORNO_DEMON_CONTA_PROC.ID_PAI (item: SQ_ITEM = sequencialItem do XML)
            -> TISS_RETORNO_DEMON_CONTA_PRC_G.ID_PAI (motivo/valor da glosa do item)
          [gatilhos TRG_TISS_RD_CTAP_GRAVA_PROC e _PROC2 disparam no INSERT do item]

  IMPORTANTE - LIMITACAO DESTE TESTE
  Nao foi encontrado, no schema DBAMV (em PRD), nenhum PACKAGE/PROCEDURE/TRIGGER que faca
  INSERT em TISS_RETORNO_DEMON_CONTA. PKG_FFCV_O_IMPORTA_TISS, que uma investigacao anterior
  (25/08/2026) supos ser a rotina de importacao, na verdade so contem uma funcao de checagem
  de privilegio (F_VERIFICA_PRIV) - nao faz parsing de XML nem INSERT.
  Conclusao: a importacao real do XML da operadora muito provavelmente acontece na camada
  Java/HTML5 do MV (fora do banco). Este script SIMULA o resultado esperado inserindo
  manualmente as linhas - ele testa se a MODELAGEM aceita os dados, mas NAO testa a logica
  de importacao real (que so e exercitada pela tela "Importar XML Recursos", que exige o
  papel 159/FFAG - ver Projetos/Recurso de Glosas/Implantacao_Recurso_Glosa_PRD.sql).

  COMO USAR
  0. ANTES de rodar o bloco principal, rode a secao "0. CHECAGEM DE PARIDADE" abaixo,
     sozinha, conectado no HML. Se algum objeto/coluna estiver faltando ali, pare e ajuste
     o script antes de continuar - a cadeia foi confirmada em PRD, nao em HML.
  1. Rodar como SCRIPT no DBeaver, aba DBMS Output habilitada, em uma sessao dedicada,
     conectado no HML (ORASML/sml).
  2. O bloco principal sempre termina em ROLLBACK - nao ha flag de aplicacao.
  3. Os SELECTs de conferencia, dentro da mesma transacao, devem mostrar os dados inseridos;
     depois do ROLLBACK, os SELECTs finais (fora da transacao) devem retornar zero linhas.
*/

---------------------------------------------------------------------------------------
-- 0. CHECAGEM DE PARIDADE (rodar isoladamente antes do bloco principal, somente leitura)
---------------------------------------------------------------------------------------
SELECT SYS_CONTEXT('USERENV','DB_NAME') AS db_name,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
  FROM dual;

SELECT table_name FROM all_tables
 WHERE owner='DBAMV'
   AND table_name IN ('TISS_MENSAGEM','TISS_RETORNO_DEMON_CONTA','TISS_RETORNO_DEMON_CONTA_GUIA',
                       'TISS_RETORNO_DEMON_CONTA_PROC','TISS_RETORNO_DEMON_CONTA_PRC_G')
 ORDER BY table_name;
-- Esperado: as 5 linhas acima. Se faltar alguma, PARE - a cadeia difere em HML.

SELECT sequence_name FROM all_sequences
 WHERE sequence_owner='DBAMV'
   AND sequence_name IN ('SEQ_TISS_MENSAGEM','SEQ_TISS_RD_CONTA','SEQ_TISS_RD_CONTA_GUIA',
                          'SEQ_TISS_RD_CONTA_PROC','SEQ_TISS_RD_CONTA_PRC_G')
 ORDER BY sequence_name;
-- Esperado: as 5 sequences acima.

SELECT trigger_name, table_name, status FROM all_triggers
 WHERE owner='DBAMV' AND trigger_name IN ('TRG_TISS_RD_CTAP_GRAVA_PROC','TRG_TISS_RD_CTAP_GRAVA_PROC2');
-- Esperado: 2 linhas, status ENABLED.

SELECT cd_convenio, nm_convenio, sn_ativo FROM dbamv.convenio WHERE cd_convenio = 20;
-- Confirma que o convenio 20 (CAPE SAUDE) tambem existe com esse codigo em HML - pode
-- divergir do PRD, confira antes de assumir.

---------------------------------------------------------------------------------------
-- BLOCO PRINCIPAL - so rodar depois que a checagem acima bater
---------------------------------------------------------------------------------------
SET SERVEROUTPUT ON;

DECLARE
    ---------------------------------------------------------------------------
    -- PARAMETROS DO TESTE (baseados no caso real, ja usado no repo XML-CAPS)
    ---------------------------------------------------------------------------
    c_cd_convenio        CONSTANT NUMBER       := 20;            -- CAPE SAUDE (conferir na secao 0)
    c_nr_protocolo       CONSTANT VARCHAR2(20) := '00000001';
    c_nr_lote            CONSTANT VARCHAR2(20) := '9001';
    c_nr_guia            CONSTANT VARCHAR2(20) := '100000';
    c_nr_guia_operadora  CONSTANT VARCHAR2(30) := '0000000100000001';
    c_cd_atendimento     CONSTANT NUMBER       := 9000001;       -- confirmado em TISS_GUIA no PRD
    c_cd_reg_fat         CONSTANT NUMBER       := 100000;
    c_sq_item_teste      CONSTANT NUMBER       := 23;            -- item real do XML (equipo)
    c_cd_procedimento    CONSTANT VARCHAR2(20) := '70222797';
    c_tp_tab_fat         CONSTANT VARCHAR2(4)  := '19';
    c_vl_informado       CONSTANT NUMBER       := 62.04;
    c_vl_glosado         CONSTANT NUMBER       := 62.04;
    c_cd_motivo_glosa    CONSTANT VARCHAR2(10) := '2012';

    l_id_mensagem         NUMBER;
    l_id_demon_conta      NUMBER;
    l_id_demon_guia       NUMBER;
    l_id_demon_proc       NUMBER;
    l_convenio            VARCHAR2(200);
    l_conta_verificacao   NUMBER;

    PROCEDURE log(p_texto VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(TO_CHAR(SYSDATE, 'DD/MM/YYYY HH24:MI:SS') || ' | ' || p_texto);
    END;
BEGIN
    SAVEPOINT antes_teste_importacao_xml;
    log('Inicio da simulacao de importacao de retorno XML em HML (sempre termina em ROLLBACK).');

    ---------------------------------------------------------------------------
    -- 1. GUARDA DE AMBIENTE - HML (ORASML/sml)
    ---------------------------------------------------------------------------
    IF SYS_CONTEXT('USERENV', 'DB_NAME') <> 'ORASML'
       OR SYS_CONTEXT('USERENV', 'SERVICE_NAME') <> 'sml' THEN
        RAISE_APPLICATION_ERROR(-20001, 'Ambiente inesperado. Este script SO roda em HML (ORASML/sml). ' ||
            'Ambiente atual: ' || SYS_CONTEXT('USERENV','DB_NAME') || '/' || SYS_CONTEXT('USERENV','SERVICE_NAME'));
    END IF;

    SELECT nm_convenio INTO l_convenio
      FROM dbamv.convenio
     WHERE cd_convenio = c_cd_convenio AND sn_ativo = 'S';
    log('Ambiente: ' || SYS_CONTEXT('USERENV','DB_NAME') || '/' || SYS_CONTEXT('USERENV','SERVICE_NAME'));
    log('Convenio: ' || c_cd_convenio || ' - ' || l_convenio);

    ---------------------------------------------------------------------------
    -- 2. ENVELOPE TISS_MENSAGEM (retorno simulado)
    ---------------------------------------------------------------------------
    SELECT dbamv.seq_tiss_mensagem.NEXTVAL INTO l_id_mensagem FROM dual;
    INSERT INTO dbamv.tiss_mensagem (
        id, tp_transacao, dt_transacao, hr_transacao, cd_convenio,
        tp_mensagem_tiss, sn_retorno, nr_lote, nr_protocolo_retorno,
        cd_status_protocolo, nm_aplicativo
    ) VALUES (
        l_id_mensagem, 'DEMONSTRATIVO_ANALISE_CONTA', TO_CHAR(SYSDATE, 'DD/MM/YYYY'), TO_CHAR(SYSDATE, 'HH24:MI'),
        c_cd_convenio, 'DEMONSTRATIVO_ANALISE_CONTA', 'S', c_nr_lote, c_nr_protocolo,
        NULL, 'TESTE_SIMULACAO_XML_CAPS_HML'
    );
    log('TISS_MENSAGEM simulada: ID=' || l_id_mensagem);

    ---------------------------------------------------------------------------
    -- 3. CABECALHO DO DEMONSTRATIVO
    ---------------------------------------------------------------------------
    SELECT dbamv.seq_tiss_rd_conta.NEXTVAL INTO l_id_demon_conta FROM dual;
    INSERT INTO dbamv.tiss_retorno_demon_conta (
        id, id_pai, nr_registro_ans, ds_operadora, nr_demonstrativo, dt_emissao,
        cd_convenio, vl_informado_fatura, vl_processado_fatura, vl_liberado_fatura, vl_glosa_fatura
    ) VALUES (
        l_id_demon_conta, l_id_mensagem, '324477',
        'CAIXA DE PREV. E ASSIT. DOS SERV. DA FUND. NACIONAL DA SAUDE',
        'TESTE-' || TO_CHAR(SYSDATE, 'YYYYMMDD'), TO_CHAR(SYSDATE, 'DD/MM/YYYY'),
        c_cd_convenio, '18994.64', '7599.68', '7599.68', '11394.96'
    );
    log('TISS_RETORNO_DEMON_CONTA simulado: ID=' || l_id_demon_conta);

    ---------------------------------------------------------------------------
    -- 4. GUIA DO DEMONSTRATIVO
    ---------------------------------------------------------------------------
    SELECT dbamv.seq_tiss_rd_conta_guia.NEXTVAL INTO l_id_demon_guia FROM dual;
    INSERT INTO dbamv.tiss_retorno_demon_conta_guia (
        id, id_pai, nr_guia, nr_guia_operadora, cd_remessa, cd_atendimento, cd_reg_fat,
        cd_convenio, vl_informado_guia, vl_processado_guia, vl_liberado_guia, vl_glosa_guia
    ) VALUES (
        l_id_demon_guia, l_id_demon_conta, c_nr_guia, c_nr_guia_operadora,
        NULL, c_cd_atendimento, c_cd_reg_fat,
        c_cd_convenio, '18994.64', '7599.68', '7599.68', '11394.96'
    );
    log('TISS_RETORNO_DEMON_CONTA_GUIA simulado: ID=' || l_id_demon_guia);

    ---------------------------------------------------------------------------
    -- 5. ITEM DO DEMONSTRATIVO (o gatilho TRG_TISS_RD_CTAP_GRAVA_PROC dispara aqui)
    ---------------------------------------------------------------------------
    SELECT dbamv.seq_tiss_rd_conta_proc.NEXTVAL INTO l_id_demon_proc FROM dual;
    INSERT INTO dbamv.tiss_retorno_demon_conta_proc (
        id, id_pai, tp_tab_fat, cd_procedimento, ds_procedimento, sq_item,
        qt_executada, vl_informado, vl_processado, vl_liberado, vl_glosado, dt_realizacao
    ) VALUES (
        l_id_demon_proc, l_id_demon_guia, c_tp_tab_fat, c_cd_procedimento,
        'TESTE SIMULACAO - EQUIPO MACROGOTAS', c_sq_item_teste,
        '1', TO_CHAR(c_vl_informado), '0', '0', TO_CHAR(c_vl_glosado), '11/05/2026'
    );
    log('TISS_RETORNO_DEMON_CONTA_PROC simulado: ID=' || l_id_demon_proc || ' (gatilhos de grava_proc devem ter disparado)');

    ---------------------------------------------------------------------------
    -- 6. MOTIVO DA GLOSA DO ITEM
    ---------------------------------------------------------------------------
    INSERT INTO dbamv.tiss_retorno_demon_conta_prc_g (
        id, id_pai, cd_motivo_glosa, ds_motivo_glosa, vl_glosa
    ) VALUES (
        dbamv.seq_tiss_rd_conta_prc_g.NEXTVAL, l_id_demon_proc, c_cd_motivo_glosa,
        'TESTE - Divergencia percentual/preco de material', TO_CHAR(c_vl_glosado)
    );
    log('TISS_RETORNO_DEMON_CONTA_PRC_G simulado.');

    ---------------------------------------------------------------------------
    -- 7. CONFERENCIA DENTRO DA MESMA TRANSACAO
    ---------------------------------------------------------------------------
    SELECT COUNT(*) INTO l_conta_verificacao
      FROM dbamv.tiss_retorno_demon_conta_proc
     WHERE id = l_id_demon_proc AND sq_item = c_sq_item_teste;
    IF l_conta_verificacao <> 1 THEN
        RAISE_APPLICATION_ERROR(-20002, 'Falha ao conferir o item simulado.');
    END IF;
    log('Item simulado conferido dentro da transacao (sq_item=' || c_sq_item_teste || ').');

    -- Se existir uma VIEW/relatorio nativo de demonstrativo, tente consulta-lo aqui dentro
    -- da transacao para ver se ele "ve" os dados simulados (ex.: V_TISS_GUIA_CONSULTA_V3,
    -- V_TISS_MOSTRA_PROTOCOLO_STATUS) - adaptar conforme o que for encontrado em HML.

    ---------------------------------------------------------------------------
    -- 8. ENCERRAMENTO - SEMPRE ROLLBACK (nao ha modo de aplicacao neste script)
    ---------------------------------------------------------------------------
    ROLLBACK TO antes_teste_importacao_xml;
    log('ROLLBACK realizado: simulacao concluida, nada foi mantido em HML.');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO antes_teste_importacao_xml;
        DBMS_OUTPUT.PUT_LINE('ERRO - alteracoes revertidas: ' || SQLERRM);
        RAISE;
END;
/

/*
  VALIDACAO POS-EXECUCAO
  Devem retornar ZERO linhas depois do ROLLBACK.
*/
SELECT * FROM dbamv.tiss_mensagem WHERE nm_aplicativo = 'TESTE_SIMULACAO_XML_CAPS_HML';
SELECT * FROM dbamv.tiss_retorno_demon_conta WHERE nr_demonstrativo LIKE 'TESTE-%';
SELECT * FROM dbamv.tiss_retorno_demon_conta_proc WHERE ds_procedimento LIKE 'TESTE SIMULACAO%';

/*
  PROXIMO PASSO SE ESTE TESTE PASSAR (opiniao, nao script)
  Se a simulacao acima rodar sem erro de constraint/trigger em HML, sabemos que a modelagem
  aceita o dado no formato esperado la tambem. Isso NAO substitui testar pela tela nativa
  "Importar XML Recursos" (que exige o papel 159/FFAG - ver
  Projetos/Recurso de Glosas/Implantacao_Recurso_Glosa_PRD.sql) - continue priorizando a
  liberacao desse acesso em HML antes de qualquer gravacao real em PRD.
*/
