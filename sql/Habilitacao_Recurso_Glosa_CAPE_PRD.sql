/*
  SOUL MV / DBAMV - HABILITACAO DO RECURSO DE GLOSA PARA CAPE SAUDE (cd_convenio=20)
  AMBIENTE: PRODUCAO (cdbprd1/prd)

  Estado entregue: SIMULACAO COM ROLLBACK POR PADRAO (c_aplicar = FALSE).
  So produz efeito permanente se voce mudar c_aplicar para TRUE deliberadamente.

  v3 (2026-09-30): corrigido ORA-00972 "identificador muito longo" - o nome do
  SAVEPOINT da v1/v2 ("antes_habilitacao_recurso_glosa", 31 caracteres) excedia o
  limite de 30 caracteres deste banco. Renomeado para "sp_recurso_glosa" (16
  caracteres) em todas as 3 ocorrencias (SAVEPOINT + 2x ROLLBACK TO).

  CONTEXTO (checado em 2026-09-29 via SELECT):
  1. dbamv.convenio.SN_IMPORTA_GLOSA_RECEB = 'N' para a CAPE (cd_convenio=20).
  2. O papel 159 "FFAG" existe e lista ~90 modulos de glosa/recurso, MAS todos com
     SN_CONSULTAR/SN_ALTERAR/SN_EXCLUIR/SN_INCLUIR = 'N'. O papel em si esta zerado.
     Este script liga so os 7 modulos MINIMOS do fluxo de recurso de glosa (nao os
     ~90 do papel inteiro):
       M_REGISTRO_RECURSO_GLOSA, M_MOT_RECURSO_GLOSA, M_JUSTIFICA_REC_GLOSA,
       M_ENTREGA_RECURSO, M_RECEBE_RECURSO, R_SINTE_RECURSO, R_ANALI_RECUR_GLOSA
     Concede consultar+incluir+alterar; NAO concede excluir (mantem trilha de auditoria).
  3. A primeira usuaria a ser habilitada (matricula F00001) nao tem o papel 159 vinculado.
  4. dbamv.motivo_recurso_glosa e dbamv.justifica_recurso_glosa continuam vazias.
  5. dbamv.convenio_conf_tiss_glosa continua sem nenhuma linha para a CAPE - NAO
     incluido neste script de proposito (decisao de negocio, tabela com auditoria
     habilitada). Ver secao final (comentada) so com as consultas de apoio.

  COMO USAR
  1. Rodar como SCRIPT no DBeaver (Alt+X - "Execute SQL Script", nao Ctrl+Enter),
     sessao dedicada. O DBMS Output do proprio DBeaver (painel/aba dele) mostra os
     logs sem precisar de "SET SERVEROUTPUT ON;" (por isso essa linha esta comentada
     abaixo - descomente so se sua instalacao do DBeaver exigir).
  2. Na primeira execucao, manter c_aplicar = FALSE. Confirme que terminou com
     "ROLLBACK realizado" e que os SELECTs de conferencia pos-execucao voltam com o
     estado ATUAL (sem mudanca).
  3. Para aplicar de verdade: (a) aprovar e substituir os textos de motivo/justificativa,
     (b) revisar a lista de modulos - adicionar/remover conforme a area de Recurso de
     Glosa confirmar o que precisa, (c) so entao mudar c_aplicar para TRUE e rodar de novo.
*/

--SET SERVEROUTPUT ON;

DECLARE
    c_aplicar               CONSTANT BOOLEAN := FALSE;

    c_cd_convenio           CONSTANT NUMBER        := 20;       -- CAPE SAUDE
    c_cd_usuario            CONSTANT VARCHAR2(30)  := 'F00001';  -- SUBSTITUIR pela matricula real do usuario a habilitar
    c_cd_papel_ffag         CONSTANT NUMBER        := 159;

    c_ds_motivo             CONSTANT VARCHAR2(240) := '[PILOTO] PREENCHER MOTIVO OFICIAL';
    c_ds_justificativa      CONSTANT VARCHAR2(240) := '[PILOTO] PREENCHER JUSTIFICATIVA OFICIAL';

    TYPE t_modulos IS TABLE OF VARCHAR2(60);
    c_modulos               CONSTANT t_modulos := t_modulos(
        'M_REGISTRO_RECURSO_GLOSA',
        'M_MOT_RECURSO_GLOSA',
        'M_JUSTIFICA_REC_GLOSA',
        'M_ENTREGA_RECURSO',
        'M_RECEBE_RECURSO',
        'R_SINTE_RECURSO',
        'R_ANALI_RECUR_GLOSA'
    );

    l_cd_motivo             NUMBER;
    l_cd_justificativa      NUMBER;
    l_quantidade            NUMBER;
    l_convenio               VARCHAR2(200);
    l_usuario                VARCHAR2(200);
    l_papel                  VARCHAR2(200);
    l_sn_importa_antes       VARCHAR2(1);

    PROCEDURE log(p_texto VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(TO_CHAR(SYSDATE, 'DD/MM/YYYY HH24:MI:SS') || ' | ' || p_texto);
    END;
BEGIN
    SAVEPOINT sp_recurso_glosa;
    log('Inicio da habilitacao controlada (c_aplicar=' || CASE WHEN c_aplicar THEN 'TRUE' ELSE 'FALSE' END || ').');

    ---------------------------------------------------------------------------
    -- 0. GUARDAS DE AMBIENTE E CADASTROS BASICOS
    ---------------------------------------------------------------------------
    IF SYS_CONTEXT('USERENV', 'DB_NAME') <> 'cdbprd1'
       OR SYS_CONTEXT('USERENV', 'SERVICE_NAME') <> 'prd' THEN
        RAISE_APPLICATION_ERROR(-20001, 'Ambiente inesperado. Script preparado para cdbprd1/prd.');
    END IF;

    SELECT nm_convenio, sn_importa_glosa_receb INTO l_convenio, l_sn_importa_antes
      FROM dbamv.convenio
     WHERE cd_convenio = c_cd_convenio AND sn_ativo = 'S';

    SELECT nm_usuario INTO l_usuario
      FROM dbasgu.usuarios
     WHERE cd_usuario = c_cd_usuario AND sn_ativo = 'S';

    SELECT ds_papel INTO l_papel
      FROM dbasgu.papel
     WHERE cd_papel = c_cd_papel_ffag AND sn_ativo = 'S';

    IF c_aplicar
       AND (INSTR(UPPER(c_ds_motivo), 'PREENCHER') > 0
            OR INSTR(UPPER(c_ds_justificativa), 'PREENCHER') > 0
            OR INSTR(UPPER(c_ds_motivo), '[PILOTO]') > 0
            OR INSTR(UPPER(c_ds_justificativa), '[PILOTO]') > 0) THEN
        RAISE_APPLICATION_ERROR(-20002, 'Aplicacao bloqueada: aprove e substitua os textos de motivo/justificativa.');
    END IF;

    log('Ambiente: ' || SYS_CONTEXT('USERENV', 'DB_NAME') || '/' || SYS_CONTEXT('USERENV', 'SERVICE_NAME'));
    log('Convenio: ' || c_cd_convenio || ' - ' || l_convenio || ' (SN_IMPORTA_GLOSA_RECEB atual: ' || l_sn_importa_antes || ')');
    log('Usuario: ' || c_cd_usuario || ' - ' || l_usuario);
    log('Papel: ' || c_cd_papel_ffag || ' - ' || l_papel);

    ---------------------------------------------------------------------------
    -- 1. PARAMETRO DO CONVENIO: LIBERAR IMPORTACAO DE GLOSA PARA A CAPE
    ---------------------------------------------------------------------------
    UPDATE dbamv.convenio
       SET sn_importa_glosa_receb = 'S'
     WHERE cd_convenio = c_cd_convenio;
    log('SN_IMPORTA_GLOSA_RECEB atualizado para S no convenio ' || c_cd_convenio || ' (' || SQL%ROWCOUNT || ' linha).');

    ---------------------------------------------------------------------------
    -- 2. PAPEL FFAG: LIGAR SO OS MODULOS MINIMOS DO FLUXO DE RECURSO DE GLOSA
    ---------------------------------------------------------------------------
    FOR i IN 1 .. c_modulos.COUNT LOOP
        UPDATE dbasgu.papel_mod
           SET sn_consultar = 'S', sn_incluir = 'S', sn_alterar = 'S'
         WHERE cd_papel = c_cd_papel_ffag
           AND cd_modulo = c_modulos(i);
        IF SQL%ROWCOUNT = 0 THEN
            log('AVISO: modulo ' || c_modulos(i) || ' nao encontrado em PAPEL_MOD para o papel ' || c_cd_papel_ffag || ' - confira o nome.');
        ELSE
            log('Modulo liberado (consultar/incluir/alterar): ' || c_modulos(i));
        END IF;
    END LOOP;

    ---------------------------------------------------------------------------
    -- 3. VINCULAR O PAPEL FFAG AO USUARIO
    ---------------------------------------------------------------------------
    SELECT COUNT(*) INTO l_quantidade
      FROM dbasgu.papel_usuarios
     WHERE cd_usuario = c_cd_usuario AND cd_papel = c_cd_papel_ffag;

    IF l_quantidade = 0 THEN
        INSERT INTO dbasgu.papel_usuarios (cd_usuario, cd_papel, tp_papel, sn_usuario_master)
             VALUES (c_cd_usuario, c_cd_papel_ffag, 'A', 'N');
        log('Papel FFAG vinculado a ' || c_cd_usuario || '.');
    ELSE
        log('Usuario ja possui o papel FFAG (nada a inserir).');
    END IF;

    ---------------------------------------------------------------------------
    -- 4. MOTIVO E JUSTIFICATIVA DE RECURSO (PILOTO)
    ---------------------------------------------------------------------------
    SELECT COUNT(*), MIN(cd_motivo_recurso_glosa)
      INTO l_quantidade, l_cd_motivo
      FROM dbamv.motivo_recurso_glosa
     WHERE UPPER(TRIM(ds_motivo_recurso_glosa)) = UPPER(TRIM(c_ds_motivo));

    IF l_quantidade = 0 THEN
        IF c_aplicar THEN
            SELECT dbamv.seq_motivo_recurso.NEXTVAL INTO l_cd_motivo FROM dual;
        ELSE
            l_cd_motivo := -900001;
        END IF;
        INSERT INTO dbamv.motivo_recurso_glosa (cd_motivo_recurso_glosa, ds_motivo_recurso_glosa)
             VALUES (l_cd_motivo, c_ds_motivo);
        log('Motivo inserido na transacao: ' || l_cd_motivo);
    ELSE
        log('Motivo ja existente; codigo reutilizado: ' || l_cd_motivo);
    END IF;

    SELECT COUNT(*), MIN(cd_justifica_recurso_glosa)
      INTO l_quantidade, l_cd_justificativa
      FROM dbamv.justifica_recurso_glosa
     WHERE UPPER(TRIM(ds_justifica_recurso_glosa)) = UPPER(TRIM(c_ds_justificativa));

    IF l_quantidade = 0 THEN
        IF c_aplicar THEN
            SELECT dbamv.seq_justifica_recurso.NEXTVAL INTO l_cd_justificativa FROM dual;
        ELSE
            l_cd_justificativa := -900002;
        END IF;
        INSERT INTO dbamv.justifica_recurso_glosa (cd_justifica_recurso_glosa, ds_justifica_recurso_glosa)
             VALUES (l_cd_justificativa, c_ds_justificativa);
        log('Justificativa inserida na transacao: ' || l_cd_justificativa);
    ELSE
        log('Justificativa ja existente; codigo reutilizado: ' || l_cd_justificativa);
    END IF;

    ---------------------------------------------------------------------------
    -- 5. CONFERENCIA DENTRO DA MESMA TRANSACAO
    ---------------------------------------------------------------------------
    SELECT sn_importa_glosa_receb INTO l_sn_importa_antes
      FROM dbamv.convenio WHERE cd_convenio = c_cd_convenio;
    IF l_sn_importa_antes <> 'S' THEN
        RAISE_APPLICATION_ERROR(-20003, 'Falha ao conferir SN_IMPORTA_GLOSA_RECEB.');
    END IF;

    SELECT COUNT(*) INTO l_quantidade
      FROM dbasgu.papel_mod
     WHERE cd_papel = c_cd_papel_ffag AND cd_modulo = 'M_REGISTRO_RECURSO_GLOSA'
       AND sn_consultar = 'S';
    IF l_quantidade <> 1 THEN
        RAISE_APPLICATION_ERROR(-20004, 'Falha ao conferir liberacao de M_REGISTRO_RECURSO_GLOSA.');
    END IF;

    log('Conferencias OK dentro da transacao.');

    ---------------------------------------------------------------------------
    -- 6. ENCERRAMENTO EXPLICITO
    ---------------------------------------------------------------------------
    IF c_aplicar THEN
        COMMIT;
        log('COMMIT realizado: habilitacao aplicada em PRD.');
    ELSE
        ROLLBACK TO sp_recurso_glosa;
        log('ROLLBACK realizado: simulacao concluida sem manter as alteracoes.');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO sp_recurso_glosa;
        DBMS_OUTPUT.PUT_LINE('ERRO - alteracoes revertidas: ' || SQLERRM);
        RAISE;
END;
/

/*
  VALIDACAO POS-EXECUCAO (com c_aplicar=FALSE, devem mostrar o estado ORIGINAL, sem mudanca)
*/
SELECT cd_convenio, nm_convenio, sn_importa_glosa_receb FROM dbamv.convenio WHERE cd_convenio = 20;

SELECT cd_papel, cd_modulo, sn_consultar, sn_incluir, sn_alterar, sn_excluir
  FROM dbasgu.papel_mod
 WHERE cd_papel = 159
   AND cd_modulo IN ('M_REGISTRO_RECURSO_GLOSA','M_MOT_RECURSO_GLOSA','M_JUSTIFICA_REC_GLOSA',
                      'M_ENTREGA_RECURSO','M_RECEBE_RECURSO','R_SINTE_RECURSO','R_ANALI_RECUR_GLOSA');

SELECT cd_usuario, cd_papel FROM dbasgu.papel_usuarios WHERE cd_usuario = 'F00001' AND cd_papel = 159;

SELECT cd_motivo_recurso_glosa, ds_motivo_recurso_glosa FROM dbamv.motivo_recurso_glosa WHERE UPPER(ds_motivo_recurso_glosa) LIKE '%PILOTO%';
SELECT cd_justifica_recurso_glosa, ds_justifica_recurso_glosa FROM dbamv.justifica_recurso_glosa WHERE UPPER(ds_justifica_recurso_glosa) LIKE '%PILOTO%';

/*
  5. MAPEAMENTO TISS DA CAPE SAUDE - NAO AUTOMATIZADO DE PROPOSITO
  Cada codigo de glosa TISS deve ser relacionado ao motivo de glosa correto do MV -
  decisao de negocio, tabela com auditoria de INSERT/UPDATE/DELETE habilitada.
  Modelo, executar somente depois de aprovar cada par:

  INSERT INTO dbamv.convenio_conf_tiss_glosa (cd_convenio, cd_glosa_tiss, cd_motivo_glosa)
       VALUES (20, <CODIGO_GLOSA_TISS>, <CODIGO_MOTIVO_MV>);
*/

-- Catalogo TISS disponivel para montagem do DE/PARA:
SELECT cd_glosa, ds_glosa FROM dbamv.glosas_tiss ORDER BY cd_glosa;

-- Motivos MV disponiveis para montagem do DE/PARA:
SELECT cd_motivo_glosa, ds_motivo_glosa FROM dbamv.motivo_glosa ORDER BY cd_motivo_glosa;

-- Configuracao atualmente existente para a CAPE (deve continuar vazio ate aprovacao):
SELECT cd_convenio, cd_glosa_tiss, cd_motivo_glosa
  FROM dbamv.convenio_conf_tiss_glosa
 WHERE cd_convenio = 20
 ORDER BY cd_glosa_tiss, cd_motivo_glosa;
