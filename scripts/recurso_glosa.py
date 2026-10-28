"""Gerador local e validador de XML TISS RECURSO_GLOSA para a CAPESESP.

Nao acessa Oracle e nao envia arquivos. O unico efeito de ``generate`` e gravar o XML
local. O comando ``mark-sent`` registra, mediante confirmacao humana, que o upload manual
foi realizado e passa a bloquear novas geracoes para o mesmo protocolo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ANS_NS = "http://www.ans.gov.br/padroes/tiss/schemas"
XML_SCHEMA_NS = "http://www.w3.org/2001/XMLSchema"
OPERADORA_NOME = "CAPESESP-CAIXA DE PREV. E ASSIST. DOS SERV. DA FUND. NAC. DE SAUDE"
DECISOES = {"RECORRER", "ACEITAR_GLOSA", "AGUARDAR_DOCUMENTACAO"}
ET.register_namespace("ans", ANS_NS)


class ValidationError(ValueError):
    """Entrada inconsistente ou regra de negocio violada."""


def q(tag: str) -> str:
    return f"{{{ANS_NS}}}{tag}"


def load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Nao foi possivel ler {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{path} deve conter um objeto JSON.")
    return value


def money(value: object, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"{field} deve ser um valor decimal valido.") from exc
    if not result.is_finite() or result.as_tuple().exponent < -2:
        raise ValidationError(f"{field} deve ter no maximo duas casas decimais.")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money_text(value: Decimal) -> str:
    return f"{value:.2f}"


def weighted_length(text: str) -> int:
    """Contagem conservadora CAPESESP: ASCII alfanumerico/espaco vale 1; demais, 2."""
    return sum(1 if (char.isascii() and (char.isalnum() or char == " ")) else 2 for char in text)


def require_text(value: object, field: str, max_length: int | None = None) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValidationError(f"{field} e obrigatorio.")
    if max_length is not None and len(result) > max_length:
        raise ValidationError(f"{field} excede {max_length} caracteres.")
    return result


def require_digits(value: object, field: str, max_length: int) -> str:
    result = require_text(value, field, max_length)
    if not result.isdigit():
        raise ValidationError(f"{field} deve conter somente digitos.")
    return result


def _contract_items(contract: dict) -> dict[int, dict]:
    if contract.get("schema_version") != "2.0":
        raise ValidationError("Contrato deve usar schema_version 2.0.")
    items = contract.get("itens")
    if not isinstance(items, list) or not items:
        raise ValidationError("Contrato sem itens.")
    indexed: dict[int, dict] = {}
    for item in items:
        try:
            seq = int(item["sequencialItem"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("Todo item do contrato deve ter sequencialItem numerico.") from exc
        if seq in indexed:
            raise ValidationError(f"sequencialItem duplicado no contrato: {seq:04d}.")
        if not 0 <= seq <= 9999:
            raise ValidationError(f"sequencialItem fora do limite de quatro digitos: {seq}.")
        if (item.get("xml") or {}).get("sequencial_item") != seq:
            raise ValidationError(f"Item {seq:04d}: sequencial interno diverge do contrato.")
        if item.get("status") not in {"CONFIRMADO", "PROVAVEL", "NAO_LOCALIZADO"}:
            raise ValidationError(f"Item {seq:04d}: status de reconciliacao invalido.")
        indexed[seq] = item
    return indexed


def decision_template(contract: dict) -> dict:
    protocol = contract.get("protocolo", {})
    guia_prestador = str(protocol.get("numero_guia_prestador") or "")
    guia_operadora = str(protocol.get("numero_guia_operadora") or "")
    generated_number = datetime.now().strftime("%y%m%d%H%M%S")
    return {
        "schema_version": "1.0",
        "cabecalho": {
            "sequencial_transacao": generated_number,
            "numero_lote_recurso": generated_number,
            "numero_guia_rec_glosa_prestador": guia_prestador,
            "numero_guia_rec_glosa_operadora": guia_prestador,
            "numero_guia_origem": guia_operadora,
            "numero_guia_operadora": guia_prestador,
            "guias_confirmadas_manualmente": False,
            "data_recurso": datetime.now().date().isoformat(),
        },
        "itens": [
            {
                "sequencialItem": seq,
                "decisao": "AGUARDAR_DOCUMENTACAO",
                "valor_recursado": "0.00",
                "justificativa": "",
                "confirmacao_manual_provavel": False,
            }
            for seq in _contract_items(contract)
        ],
    }


def _add(parent: ET.Element, tag: str, text: object) -> ET.Element:
    element = ET.SubElement(parent, q(tag))
    element.text = str(text)
    return element


def _is_sent(registry: Path | None, protocolo: str) -> bool:
    if registry is None or not registry.exists():
        return False
    with closing(sqlite3.connect(registry)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS envios (protocolo TEXT PRIMARY KEY, xml_sha256 TEXT NOT NULL, enviado_em TEXT NOT NULL)"
            )
            return connection.execute(
                "SELECT 1 FROM envios WHERE protocolo = ?", (protocolo,)
            ).fetchone() is not None


def _validate_inputs(contract: dict, decisions: dict, registry: Path | None) -> tuple[dict, list[tuple[dict, dict, Decimal]], list[str]]:
    if decisions.get("schema_version") != "1.0":
        raise ValidationError("Decisoes devem usar schema_version 1.0.")
    protocol = contract.get("protocolo")
    if not isinstance(protocol, dict):
        raise ValidationError("Contrato sem protocolo.")
    numero_protocolo = require_digits(protocol.get("numero_protocolo"), "numero_protocolo", 12)
    if _is_sent(registry, numero_protocolo):
        raise ValidationError(f"O protocolo {numero_protocolo} ja foi marcado como enviado.")
    if require_text(protocol.get("padrao_tiss"), "padrao_tiss") != "4.01.00":
        raise ValidationError("Este gerador aceita somente contratos TISS 4.01.00.")
    if require_digits(protocol.get("registro_ans_operadora"), "registro_ans_operadora", 6) != "324477":
        raise ValidationError("O contrato nao pertence a CAPESESP (ANS 324477).")
    cnpj = require_digits(protocol.get("cnpj_prestador"), "cnpj_prestador", 14)
    if len(cnpj) != 14:
        raise ValidationError("cnpj_prestador deve ter 14 digitos.")

    header = decisions.get("cabecalho")
    if not isinstance(header, dict):
        raise ValidationError("Decisoes sem cabecalho.")
    if header.get("guias_confirmadas_manualmente") is not True:
        raise ValidationError("Confirme manualmente o DE/PARA das guias J/K antes de gerar.")
    normalized_header = {
        "sequencial_transacao": require_digits(header.get("sequencial_transacao"), "sequencial_transacao", 12),
        "numero_lote_recurso": require_digits(header.get("numero_lote_recurso"), "numero_lote_recurso", 12),
        "numero_guia_rec_glosa_prestador": require_text(header.get("numero_guia_rec_glosa_prestador"), "numero_guia_rec_glosa_prestador", 20),
        "numero_guia_rec_glosa_operadora": require_text(header.get("numero_guia_rec_glosa_operadora"), "numero_guia_rec_glosa_operadora", 20),
        "numero_guia_origem": require_text(header.get("numero_guia_origem"), "numero_guia_origem", 20),
        "numero_guia_operadora": require_text(header.get("numero_guia_operadora"), "numero_guia_operadora", 20),
        "data_recurso": require_text(header.get("data_recurso"), "data_recurso", 10),
        "cnpj": cnpj,
        "protocolo": numero_protocolo,
    }
    try:
        datetime.strptime(normalized_header["data_recurso"], "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError("data_recurso deve estar em YYYY-MM-DD.") from exc
    lote_original = str(protocol.get("numero_lote_prestador") or "")
    if normalized_header["numero_lote_recurso"] == lote_original:
        raise ValidationError("numero_lote_recurso nao pode repetir o lote original.")

    contract_items = _contract_items(contract)
    raw_decisions = decisions.get("itens")
    if not isinstance(raw_decisions, list):
        raise ValidationError("Decisoes sem lista de itens.")
    indexed_decisions: dict[int, dict] = {}
    for decision in raw_decisions:
        try:
            seq = int(decision["sequencialItem"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("Decisao com sequencialItem invalido.") from exc
        if seq in indexed_decisions:
            raise ValidationError(f"Decisao duplicada para o item {seq:04d}.")
        if seq not in contract_items:
            raise ValidationError(f"Decisao referencia item inexistente: {seq:04d}.")
        indexed_decisions[seq] = decision
    missing = sorted(set(contract_items) - set(indexed_decisions))
    if missing:
        raise ValidationError(f"Faltam decisoes para {len(missing)} itens: {missing[:10]}.")

    selected: list[tuple[dict, dict, Decimal]] = []
    warnings: list[str] = []
    for seq, item in contract_items.items():
        decision = indexed_decisions[seq]
        action = decision.get("decisao")
        if action not in DECISOES:
            raise ValidationError(f"Decisao invalida para item {seq:04d}: {action!r}.")
        if action != "RECORRER":
            continue
        status = item.get("status")
        if status == "NAO_LOCALIZADO":
            raise ValidationError(f"Item {seq:04d} NAO_LOCALIZADO nao pode ser recorrido.")
        if status == "PROVAVEL" and decision.get("confirmacao_manual_provavel") is not True:
            raise ValidationError(f"Item {seq:04d} PROVAVEL exige confirmacao manual explicita.")
        xml = item.get("xml") or {}
        if decision.get("codigo_procedimento") not in (None, xml.get("codigo_procedimento")):
            raise ValidationError(f"Item {seq:04d}: codigo_procedimento foi alterado.")
        glosa = money(xml.get("valor_glosa"), f"item {seq:04d}.valor_glosa")
        value = money(decision.get("valor_recursado"), f"item {seq:04d}.valor_recursado")
        if value <= 0 or value > glosa:
            raise ValidationError(f"Item {seq:04d}: valor recursado deve ser maior que zero e no maximo {money_text(glosa)}.")
        if value > Decimal("999999.99"):
            raise ValidationError(f"Item {seq:04d}: valor recursado excede o limite do XSD.")
        justification = require_text(decision.get("justificativa"), f"item {seq:04d}.justificativa")
        count = weighted_length(justification)
        if count > 150:
            raise ValidationError(f"Item {seq:04d}: justificativa vale {count}/150 caracteres CAPESESP.")
        try:
            justification.encode("iso-8859-1")
        except UnicodeEncodeError as exc:
            raise ValidationError(f"Item {seq:04d}: justificativa contem caractere fora de ISO-8859-1.") from exc
        description = require_text(xml.get("descricao_procedimento"), f"item {seq:04d}.descricao_procedimento")
        if len(description) > 150:
            warnings.append(f"Item {seq:04d}: descricao truncada de {len(description)} para 150 caracteres (limite XSD).")
        selected.append((item, decision, value))
    if not selected:
        raise ValidationError("Nenhum item foi marcado como RECORRER.")
    return normalized_header, selected, warnings


def calculate_hash(root: ET.Element) -> str:
    hash_element = root.find(f".//{q('hash')}")
    values = [element.text or "" for element in root.iter() if len(element) == 0 and element is not hash_element]
    return hashlib.md5("".join(values).encode("iso-8859-1")).hexdigest()


def generate_xml(contract: dict, decisions: dict, registry: Path | None = None) -> tuple[bytes, list[str]]:
    header, selected, warnings = _validate_inputs(contract, decisions, registry)
    now_value = decisions.get("gerado_em")
    try:
        now = datetime.fromisoformat(now_value) if now_value else datetime.now()
    except (TypeError, ValueError) as exc:
        raise ValidationError("gerado_em deve ser uma data/hora ISO valida.") from exc

    root = ET.Element(q("mensagemTISS"), {"xmlns": XML_SCHEMA_NS})
    cabecalho = ET.SubElement(root, q("cabecalho"))
    transacao = ET.SubElement(cabecalho, q("identificacaoTransacao"))
    _add(transacao, "tipoTransacao", "RECURSO_GLOSA")
    _add(transacao, "sequencialTransacao", header["sequencial_transacao"])
    _add(transacao, "dataRegistroTransacao", now.date().isoformat())
    _add(transacao, "horaRegistroTransacao", now.strftime("%H:%M:%S"))
    origem = ET.SubElement(cabecalho, q("origem"))
    identificacao = ET.SubElement(origem, q("identificacaoPrestador"))
    _add(identificacao, "CNPJ", header["cnpj"])
    destino = ET.SubElement(cabecalho, q("destino"))
    _add(destino, "registroANS", "324477")
    _add(cabecalho, "Padrao", "4.01.00")

    prestador = ET.SubElement(root, q("prestadorParaOperadora"))
    recurso = ET.SubElement(prestador, q("recursoGlosa"))
    guia = ET.SubElement(recurso, q("guiaRecursoGlosa"))
    _add(guia, "registroANS", "324477")
    _add(guia, "numeroGuiaRecGlosaPrestador", header["numero_guia_rec_glosa_prestador"])
    _add(guia, "nomeOperadora", OPERADORA_NOME)
    _add(guia, "objetoRecurso", "2")
    _add(guia, "numeroGuiaRecGlosaOperadora", header["numero_guia_rec_glosa_operadora"])
    contratado = ET.SubElement(guia, q("dadosContratado"))
    _add(contratado, "cnpjContratado", header["cnpj"])
    _add(guia, "numeroLote", header["numero_lote_recurso"])
    _add(guia, "numeroProtocolo", header["protocolo"])
    opcao = ET.SubElement(guia, q("opcaoRecurso"))
    recurso_guia = ET.SubElement(opcao, q("recursoGuia"))
    _add(recurso_guia, "numeroGuiaOrigem", header["numero_guia_origem"])
    _add(recurso_guia, "numeroGuiaOperadora", header["numero_guia_operadora"])
    opcao_guia = ET.SubElement(recurso_guia, q("opcaoRecursoGuia"))
    total = Decimal("0.00")
    for item, decision, value in selected:
        xml = item["xml"]
        seq = int(item["sequencialItem"])
        data_realizacao = require_text(xml.get("data_realizacao"), f"item {seq:04d}.data_realizacao")
        try:
            datetime.strptime(data_realizacao, "%Y-%m-%d")
        except ValueError as exc:
            raise ValidationError(f"Item {seq:04d}: data_realizacao deve estar em YYYY-MM-DD.") from exc
        item_el = ET.SubElement(opcao_guia, q("itensGuia"))
        _add(item_el, "sequencialItem", f"{seq:04d}")
        _add(item_el, "dataInicio", data_realizacao)
        proc = ET.SubElement(item_el, q("procRecurso"))
        _add(proc, "codigoTabela", require_text(xml.get("codigo_tabela"), f"item {seq:04d}.codigo_tabela"))
        _add(proc, "codigoProcedimento", require_text(xml.get("codigo_procedimento"), f"item {seq:04d}.codigo_procedimento", 10))
        description = require_text(xml.get("descricao_procedimento"), f"item {seq:04d}.descricao_procedimento")[:150]
        _add(proc, "descricaoProcedimento", description)
        _add(item_el, "codGlosaItem", require_digits(xml.get("tipo_glosa"), f"item {seq:04d}.tipo_glosa", 4))
        _add(item_el, "valorRecursado", money_text(value))
        _add(item_el, "justificativaItem", require_text(decision.get("justificativa"), f"item {seq:04d}.justificativa"))
        total += value
    if total > Decimal("99999999.99"):
        raise ValidationError("valorTotalRecursado excede o limite do XSD.")
    _add(guia, "valorTotalRecursado", money_text(total))
    _add(guia, "dataRecurso", header["data_recurso"])
    epilogo = ET.SubElement(root, q("epilogo"))
    hash_element = _add(epilogo, "hash", "")
    ET.indent(root, space="  ")
    hash_element.text = calculate_hash(root)
    try:
        payload = ET.tostring(root, encoding="ISO-8859-1", xml_declaration=True)
    except UnicodeEncodeError as exc:
        raise ValidationError("O XML contem texto nao representavel em ISO-8859-1.") from exc
    return payload, warnings


def validate_xsd_payload(payload: bytes, xsd_path: Path) -> None:
    try:
        from lxml import etree
    except ImportError as exc:
        raise ValidationError("Instale lxml para validar contra XSD: pip install -r requirements.txt") from exc
    try:
        schema = etree.XMLSchema(etree.parse(str(xsd_path)))
        document = etree.ElementTree(etree.fromstring(payload))
    except (OSError, etree.XMLSyntaxError) as exc:
        raise ValidationError(f"Nao foi possivel carregar XML/XSD: {exc}") from exc
    if not schema.validate(document):
        errors = "; ".join(error.message for error in schema.error_log[:5])
        raise ValidationError(f"XML invalido no XSD TISS: {errors}")


def validate_xsd(xml_path: Path, xsd_path: Path) -> None:
    try:
        payload = xml_path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"Nao foi possivel ler o XML: {exc}") from exc
    validate_xsd_payload(payload, xsd_path)


def mark_sent(registry: Path, protocolo: str, xml_path: Path) -> None:
    protocolo = require_digits(protocolo, "protocolo", 12)
    if not xml_path.exists():
        raise ValidationError(f"XML nao encontrado: {xml_path}")
    registry.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(xml_path.read_bytes()).hexdigest()
    try:
        with closing(sqlite3.connect(registry)) as connection:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS envios (protocolo TEXT PRIMARY KEY, xml_sha256 TEXT NOT NULL, enviado_em TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO envios VALUES (?, ?, ?)",
                    (protocolo, digest, datetime.now().isoformat(timespec="seconds")),
                )
    except sqlite3.IntegrityError as exc:
        raise ValidationError(f"O protocolo {protocolo} ja foi marcado como enviado.") from exc


def main(argv: list[str] | None = None) -> int:
    root_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="Cria um JSON de decisoes para revisao no painel.")
    template.add_argument("--contract", type=Path, default=root_dir / "output" / "glosa_reconciliation.json")
    template.add_argument("--out", type=Path, default=root_dir / "output" / "decisoes_recurso.json")
    generate = sub.add_parser("generate", help="Valida as decisoes e gera XML local (dry-run).")
    generate.add_argument("--contract", type=Path, default=root_dir / "output" / "glosa_reconciliation.json")
    generate.add_argument("--decisions", type=Path, default=root_dir / "output" / "decisoes_recurso.json")
    generate.add_argument("--out", type=Path, default=root_dir / "output" / "recurso_glosa.xml")
    generate.add_argument(
        "--xsd",
        type=Path,
        default=root_dir / "xsd" / "tiss_v4_03_00" / "tissV4_03_00.xsd",
        help="Schema TISS oficial da ANS. Passe vazio/inexistente para pular a validacao.",
    )
    generate.add_argument("--registry", type=Path, default=root_dir / "output" / "submission_registry.sqlite3")
    sent = sub.add_parser("mark-sent", help="Registra que o XML foi enviado manualmente no portal.")
    sent.add_argument("--protocol", required=True)
    sent.add_argument("--xml", type=Path, required=True)
    sent.add_argument("--registry", type=Path, default=root_dir / "output" / "submission_registry.sqlite3")
    sent.add_argument("--confirm-uploaded", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            data = decision_template(load_json(args.contract))
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Template gravado em: {args.out}")
        elif args.command == "generate":
            payload, warnings = generate_xml(load_json(args.contract), load_json(args.decisions), args.registry)
            if args.xsd and args.xsd.exists():
                validate_xsd_payload(payload, args.xsd)
            else:
                warnings.append(f"Validacao XSD nao executada; schema nao encontrado em {args.xsd}.")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_bytes(payload)
            for warning in warnings:
                print(f"AVISO: {warning}", file=sys.stderr)
            print(f"DRY RUN: XML gravado em {args.out}; nenhum envio foi realizado.")
        else:
            mark_sent(args.registry, args.protocol, args.xml)
            print(f"Protocolo {args.protocol} marcado como enviado manualmente.")
    except ValidationError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
