"""
Reconciliacao XML CAPE (DEMONSTRATIVO_ANALISE_CONTA) <-> Oracle Soul MV, somente leitura.

Contexto: o modulo nativo de Recurso de Glosa do MV esta implantado mas sem uso em
producao para a CAPE SAUDE (ver plano em
C:\\Users\\emers\\.claude\\plans\\voc-est-atuando-como-robust-rocket.md e o projeto
anterior mais completo em C:\\Users\\emers\\Projetos\\Recurso de Glosas\\). Este script
gera o contrato `glosa_reconciliation.json` que o Codex consome para montar o gerador de
XML de RECURSO_GLOSA e o painel do analista, sem que o Codex precise de acesso ao Oracle.

NUNCA escreve no banco. NUNCA abre uma conexao Oracle propria/nova - o unico jeito
autorizado de obter dado real do MV e (a) o MCP soul-mv-erp desta sessao, ou (b) reusar
o projeto que ja tem a conexao configurada, C:\\Users\\emers\\Projetos\\erp-mcp-server
(mesmo padrao usado em Projetos/Recurso de Glosas/diagnostico_mcp_readonly.py). Duas
fontes de dados sao suportadas aqui:

  1. JsonFixtureGateway (padrao, usado nesta sessao): le os dumps ja exportados via MCP
     (somente leitura) em data/oracle_dump/*.json - reprodutivel sem credencial de banco.
  2. ErpMcpServerGateway (opcional, ainda NAO EXERCITADO nesta sessao): importa
     tools.soul_mv de erp-mcp-server e roda a mesma consulta ao vivo, sem duplicar
     configuracao de conexao.

Uso:
    python scripts/reconcile_glosa.py --xml "C:\\caminho\\para\\o\\demonstrativo.xml"
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

NS = {"ans": "http://www.ans.gov.br/padroes/tiss/schemas"}

# Tabelas TISS que caem em cada tabela nativa do MV (confirmado empiricamente no
# caso-piloto): procedimentos clinicos (tabela 22) vivem em TISS_ITGUIA;
# materiais/medicamentos/outras despesas (19, 20, 00, 18...) vivem em TISS_ITGUIA_OUT.
PROCEDIMENTO_TABELAS = {"22"}


@dataclass
class XmlItem:
    sequencial_item: int
    data_realizacao: str
    codigo_tabela: str
    codigo_procedimento: str
    descricao_procedimento: str
    valor_informado: str
    valor_glosa: str
    tipo_glosa: str | None


@dataclass
class OracleItem:
    sq_item: int
    tp_tab_fat: str | None
    cd_procedimento: str
    vl_total: str
    dt_realizado: str
    origem_tabela: str  # 'TISS_ITGUIA' ou 'TISS_ITGUIA_OUT'


@dataclass
class Reconciliacao:
    sequencial_item: int
    status: str  # CONFIRMADO | PROVAVEL | NAO_LOCALIZADO
    xml: dict = field(default_factory=dict)
    oracle: dict | None = None
    motivo: str = ""


class JsonFixtureGateway:
    """Le os dumps somente-leitura ja exportados do Oracle (data/oracle_dump/)."""

    def __init__(self, base_dir: Path, numero_guia: str):
        self.itguia = self._load(base_dir / f"tiss_itguia_guia_{numero_guia}.json", "TISS_ITGUIA")
        self.itguia_out = self._load(
            base_dir / f"tiss_itguia_out_guia_{numero_guia}.json", "TISS_ITGUIA_OUT"
        )
        todos = self.itguia + self.itguia_out
        sequenciais = [item.sq_item for item in todos]
        duplicados = sorted({seq for seq in sequenciais if sequenciais.count(seq) > 1})
        if duplicados:
            raise ValueError(f"SQ_ITEM duplicado nos dumps: {duplicados}")
        self.by_sq_item = {i.sq_item: i for i in todos}

    @staticmethod
    def _load(path: Path, origem: str) -> list[OracleItem]:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        return [
            OracleItem(
                sq_item=r["sq_item"],
                tp_tab_fat=r.get("tp_tab_fat"),
                cd_procedimento=(r["cd_procedimento"] or "").strip(),
                vl_total=str(r["vl_total"]),
                dt_realizado=r["dt_realizado"],
                origem_tabela=origem,
            )
            for r in rows
        ]

    def buscar_item(self, sequencial_item: int) -> OracleItem | None:
        return self.by_sq_item.get(sequencial_item)


class ErpMcpServerGateway:
    """
    Alternativa para rodar direto contra o Oracle (NAO EXERCITADA nesta sessao).

    NAO cria uma conexao Oracle propria. O unico jeito autorizado de falar com o MV
    fora do MCP desta sessao e reusar o projeto que ja tem a conexao configurada:
    C:\\Users\\emers\\Projetos\\erp-mcp-server (mesmo backend por tras das tools
    mcp__soul-mv-erp__*, com credenciais em erp-mcp-server/.env). E o mesmo padrao
    usado em Projetos/Recurso de Glosas/diagnostico_mcp_readonly.py.

    Nunca escrever um novo cliente Oracle/oracledb/DSN neste repositorio.
    """

    ERP_MCP_ROOT = Path(r"C:\Users\emers\Projetos\erp-mcp-server")

    def __init__(self, id_guia: int):
        if str(self.ERP_MCP_ROOT) not in sys.path:
            sys.path.insert(0, str(self.ERP_MCP_ROOT))
        from tools.soul_mv import executar_sql_livre  # type: ignore  # noqa: E402

        self._executar_sql_livre = executar_sql_livre
        self.id_guia = id_guia

    def buscar_item(self, sequencial_item: int) -> OracleItem | None:
        for tabela in ("DBAMV.TISS_ITGUIA", "DBAMV.TISS_ITGUIA_OUT"):
            sql = f"""
                SELECT SQ_ITEM, TP_TAB_FAT, CD_PROCEDIMENTO, VL_TOTAL, DT_REALIZADO
                FROM {tabela}
                WHERE ID_PAI = {self.id_guia} AND SQ_ITEM = {sequencial_item}
            """
            rows = self._executar_sql_livre(sql)
            if rows:
                r = rows[0]
                return OracleItem(
                    sq_item=r["sq_item"],
                    tp_tab_fat=r.get("tp_tab_fat"),
                    cd_procedimento=(r["cd_procedimento"] or "").strip(),
                    vl_total=str(r["vl_total"]),
                    dt_realizado=str(r["dt_realizado"]),
                    origem_tabela=tabela.split(".")[-1],
                )
        return None


def parse_xml(xml_path: Path) -> tuple[dict, list[XmlItem]]:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    tipo_transacao = root.findtext("./ans:cabecalho/ans:identificacaoTransacao/ans:tipoTransacao", namespaces=NS)
    if tipo_transacao != "DEMONSTRATIVO_ANALISE_CONTA":
        raise ValueError("Envie um XML TISS do tipo DEMONSTRATIVO_ANALISE_CONTA.")

    protocolo_el = root.find(".//ans:dadosProtocolo", NS)
    guias = root.findall(".//ans:relacaoGuias", NS)
    if protocolo_el is None or len(guias) != 1:
        raise ValueError("O contrato exige exatamente um dadosProtocolo e uma relacaoGuias.")
    guia_el = guias[0]
    origem = root.find("./ans:cabecalho/ans:origem", NS)
    destino = root.find("./ans:cabecalho/ans:destino", NS)

    header = {
        "numero_lote_prestador": protocolo_el.findtext("ans:numeroLotePrestador", namespaces=NS),
        "numero_protocolo": protocolo_el.findtext("ans:numeroProtocolo", namespaces=NS),
        "numero_guia_prestador": guia_el.findtext("ans:numeroGuiaPrestador", namespaces=NS),
        "numero_guia_operadora": guia_el.findtext("ans:numeroGuiaOperadora", namespaces=NS),
        "registro_ans_operadora": origem.findtext("ans:registroANS", namespaces=NS) if origem is not None else None,
        "cnpj_prestador": destino.findtext(".//ans:CNPJ", namespaces=NS) if destino is not None else None,
        "padrao_tiss": root.findtext("./ans:cabecalho/ans:Padrao", namespaces=NS),
    }

    itens = []
    for detalhe in guia_el.findall("ans:detalhesGuia", NS):
        seq = int(detalhe.findtext("ans:sequencialItem", namespaces=NS))
        proc = detalhe.find("ans:procedimento", NS)
        glosas = detalhe.findall("ans:relacaoGlosa", NS)
        if len(glosas) > 1:
            raise ValueError(f"Item {seq:04d} possui mais de uma relacaoGlosa.")
        glosa = glosas[0] if glosas else None
        itens.append(
            XmlItem(
                sequencial_item=seq,
                data_realizacao=detalhe.findtext("ans:dataRealizacao", namespaces=NS),
                codigo_tabela=proc.findtext("ans:codigoTabela", namespaces=NS),
                codigo_procedimento=proc.findtext("ans:codigoProcedimento", namespaces=NS),
                descricao_procedimento=proc.findtext("ans:descricaoProcedimento", namespaces=NS),
                valor_informado=detalhe.findtext("ans:valorInformado", namespaces=NS),
                valor_glosa=glosa.findtext("ans:valorGlosa", namespaces=NS) if glosa is not None else "0.00",
                tipo_glosa=glosa.findtext("ans:tipoGlosa", namespaces=NS) if glosa is not None else None,
            )
        )
    return header, itens


def build_contract(xml_path: Path, oracle_dump_dir: Path) -> dict:
    """Monta o contrato tecnico sem gravar no MV nem preservar o XML de origem."""
    header, itens = parse_xml(xml_path)
    gateway = JsonFixtureGateway(oracle_dump_dir, header["numero_guia_prestador"])
    resultados = reconciliar(itens, gateway)
    contagem = {"CONFIRMADO": 0, "PROVAVEL": 0, "NAO_LOCALIZADO": 0}
    for resultado in resultados:
        contagem[resultado.status] += 1
    return {
        "schema_version": "2.0",
        "_gerado_por": "scripts/reconcile_glosa.py (somente leitura, sem escrita no MV)",
        "protocolo": header,
        "resumo": {"total_itens": len(resultados), **contagem},
        "itens": [
            {
                "sequencialItem": resultado.sequencial_item,
                "status": resultado.status,
                "motivo": resultado.motivo,
                "xml": resultado.xml,
                "oracle": resultado.oracle,
            }
            for resultado in resultados
        ],
    }


def reconciliar(itens: list[XmlItem], gateway: JsonFixtureGateway) -> list[Reconciliacao]:
    resultados = []
    for item in itens:
        oracle_item = gateway.buscar_item(item.sequencial_item)

        if oracle_item is None:
            resultados.append(
                Reconciliacao(
                    sequencial_item=item.sequencial_item,
                    status="NAO_LOCALIZADO",
                    xml=item.__dict__,
                    motivo="Nenhum SQ_ITEM correspondente em TISS_ITGUIA/TISS_ITGUIA_OUT para essa guia.",
                )
            )
            continue

        mesmo_codigo = oracle_item.cd_procedimento == item.codigo_procedimento
        mesmo_valor = Decimal(oracle_item.vl_total) == Decimal(item.valor_informado)
        mesma_data = oracle_item.dt_realizado == item.data_realizacao
        tabela_esperada = (
            "TISS_ITGUIA" if item.codigo_tabela in PROCEDIMENTO_TABELAS else "TISS_ITGUIA_OUT"
        )
        tabela_ok = oracle_item.origem_tabela == tabela_esperada

        if mesmo_codigo and mesmo_valor and mesma_data and tabela_ok:
            status, motivo = "CONFIRMADO", "codigoProcedimento, valor, data e tabela batem exatamente."
        elif mesmo_valor and mesma_data and tabela_ok:
            # ATENCAO: valor batendo sozinho e evidencia fraca - varios itens de baixo valor
            # (ex.: R$2.54, R$1.27, R$28.00) se repetem entre procedimentos diferentes na
            # mesma data, entao esse match pode ser coincidencia e nao recodificacao real.
            # Confirmado nesta sessao com casos onde a DESCRICAO do item diverge por completo
            # (ex.: sequencialItem 0104 = luva cirurgica no XML vs sonda de aspiracao no
            # Oracle) mesmo com data e valor identicos - exige checagem manual item a item
            # antes de qualquer decisao de recurso.
            status, motivo = (
                "PROVAVEL",
                f"SQ_ITEM/data batem, mas codigoProcedimento diverge (XML={item.codigo_procedimento} "
                f"vs Oracle={oracle_item.cd_procedimento}) - pode ser recodificacao de tabela "
                f"propria (tabela '00') OU coincidencia de valor entre itens diferentes na "
                f"mesma data. NAO tratar como confirmado sem checagem manual da descricao.",
            )
        else:
            status, motivo = "PROVAVEL", "Item encontrado no SQ_ITEM, mas valor/tabela divergem - checar manualmente."

        resultados.append(
            Reconciliacao(
                sequencial_item=item.sequencial_item,
                status=status,
                xml=item.__dict__,
                oracle=oracle_item.__dict__,
                motivo=motivo,
            )
        )
    return resultados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xml",
        type=Path,
        required=True,
        help="Caminho do XML DEMONSTRATIVO_ANALISE_CONTA da CAPE (nao versionado no repo).",
    )
    parser.add_argument(
        "--oracle-dump-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "oracle_dump",
        help="Diretorio com os dumps JSON somente-leitura exportados do Oracle.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "glosa_reconciliation.json",
        help="Onde gravar o contrato JSON de saida (consumido pelo Codex).",
    )
    args = parser.parse_args()

    if not args.xml.exists():
        print(f"XML nao encontrado: {args.xml}", file=sys.stderr)
        return 1

    saida = build_contract(args.xml, args.oracle_dump_dir)
    header = saida["protocolo"]
    contagem = {key: saida["resumo"][key] for key in ("CONFIRMADO", "PROVAVEL", "NAO_LOCALIZADO")}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(f"Protocolo {header['numero_protocolo']} / guia {header['numero_guia_prestador']}")
    print(f"Itens: {contagem}")
    print(f"Saida gravada em: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
