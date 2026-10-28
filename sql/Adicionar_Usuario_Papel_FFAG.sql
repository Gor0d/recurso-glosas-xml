/*
  SOUL MV / DBAMV - VINCULAR PAPEL FFAG (159) A UM USUARIO ADICIONAL
  AMBIENTE: PRODUCAO (cdbprd1/prd)

  Pre-requisito ja atendido (feito uma vez so, em 2026-10-02, pela primeira
  usuaria habilitada): convenio CAPE liberado, os 7 modulos do papel 159
  liberados, motivo/justificativa cadastrados. Este script so faz UMA coisa:
  vincula o papel 159 a um usuario novo (nao repete o resto).

  Estado entregue: SIMULACAO COM ROLLBACK POR PADRAO (c_aplicar = FALSE).
  Troque para TRUE so depois de confirmar a simulacao.

  COMO USAR: Alt+X no DBeaver (nao Ctrl+Enter), sessao dedicada.
*/

DECLARE
    c_aplicar               CONSTANT BOOLEAN := FALSE;

    c_cd_usuario            CONSTANT VARCHAR2(30) := 'F00002';  -- SUBSTITUIR pela matricula real do usuario a habilitar
    c_cd_papel_ffag         CONSTANT NUMBER        := 159;

    l_usuario                VARCHAR2(200);
    l_papel                  VARCHAR2(200);
    l_quantidade             NUMBER;

    PROCEDURE log(p_texto VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(TO_CHAR(SYSDATE, 'DD/MM/YYYY HH24:MI:SS') || ' | ' || p_texto);
    END;
BEGIN
    SAVEPOINT sp_add_usuario_ffag;
    log('Inicio (c_aplicar=' || CASE WHEN c_aplicar THEN 'TRUE' ELSE 'FALSE' END || ').');

    IF SYS_CONTEXT('USERENV', 'DB_NAME') <> 'cdbprd1'
       OR SYS_CONTEXT('USERENV', 'SERVICE_NAME') <> 'prd' THEN
        RAISE_APPLICATION_ERROR(-20001, 'Ambiente inesperado. Script preparado para cdbprd1/prd.');
    END IF;

    SELECT nm_usuario INTO l_usuario
      FROM dbasgu.usuarios
     WHERE cd_usuario = c_cd_usuario AND sn_ativo = 'S';

    SELECT ds_papel INTO l_papel
      FROM dbasgu.papel
     WHERE cd_papel = c_cd_papel_ffag AND sn_ativo = 'S';

    log('Usuario: ' || c_cd_usuario || ' - ' || l_usuario);
    log('Papel: ' || c_cd_papel_ffag || ' - ' || l_papel);

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

    SELECT COUNT(*) INTO l_quantidade
      FROM dbasgu.papel_usuarios
     WHERE cd_usuario = c_cd_usuario AND cd_papel = c_cd_papel_ffag;
    IF l_quantidade <> 1 THEN
        RAISE_APPLICATION_ERROR(-20002, 'Falha ao conferir o vinculo do papel.');
    END IF;
    log('Conferencia OK dentro da transacao.');

    IF c_aplicar THEN
        COMMIT;
        log('COMMIT realizado: usuario vinculado em PRD.');
    ELSE
        ROLLBACK TO sp_add_usuario_ffag;
        log('ROLLBACK realizado: simulacao concluida sem manter a alteracao.');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO sp_add_usuario_ffag;
        DBMS_OUTPUT.PUT_LINE('ERRO - alteracoes revertidas: ' || SQLERRM);
        RAISE;
END;
/

SELECT cd_usuario, cd_papel, tp_papel FROM dbasgu.papel_usuarios WHERE cd_usuario = 'F00002' AND cd_papel = 159;
