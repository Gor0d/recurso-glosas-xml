"""Painel web local para revisar glosas e gerar o XML em dry-run."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
from datetime import datetime
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from xml.etree.ElementTree import ParseError

from auth import AuthError, AuthStore, SESSION_SECONDS
from reconcile_glosa import build_contract
from recurso_glosa import ValidationError, decision_template, generate_xml, load_json, validate_xsd_payload


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_bi_csv(contract: dict, decisions: dict, glossary: dict | None = None) -> bytes:
    """Exporta uma tabela achatada, estavel e amigavel ao Power BI/Excel."""
    decision_by_item = {
        int(item.get("sequencialItem")): item
        for item in decisions.get("itens", [])
        if item.get("sequencialItem") is not None
    }
    protocol = contract.get("protocolo", {})
    focus_by_code = {
        str(item.get("codigo")): item.get("linha", "")
        for item in (glossary or {}).get("catalogo_foco", [])
    }
    output = io.StringIO(newline="")
    fields = [
        "numero_protocolo", "numero_lote_prestador", "numero_guia_prestador",
        "registro_ans_operadora", "padrao_tiss", "sequencial_item", "status_conciliacao",
        "motivo_conciliacao", "data_realizacao", "codigo_tabela", "codigo_procedimento",
        "descricao_procedimento", "codigo_glosa", "linha_foco", "valor_informado", "valor_glosa",
        "origem_mv", "decisao", "valor_recursado", "justificativa",
        "confirmacao_manual_provavel",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, delimiter=";", lineterminator="\r\n")
    writer.writeheader()
    for item in contract.get("itens", []):
        xml = item.get("xml") or {}
        oracle = item.get("oracle") or {}
        decision = decision_by_item.get(int(item.get("sequencialItem", 0)), {})
        writer.writerow({
            "numero_protocolo": protocol.get("numero_protocolo", ""),
            "numero_lote_prestador": protocol.get("numero_lote_prestador", ""),
            "numero_guia_prestador": protocol.get("numero_guia_prestador", ""),
            "registro_ans_operadora": protocol.get("registro_ans_operadora", ""),
            "padrao_tiss": protocol.get("padrao_tiss", ""),
            "sequencial_item": item.get("sequencialItem", ""),
            "status_conciliacao": item.get("status", ""),
            "motivo_conciliacao": item.get("motivo", ""),
            "data_realizacao": xml.get("data_realizacao", ""),
            "codigo_tabela": xml.get("codigo_tabela", ""),
            "codigo_procedimento": xml.get("codigo_procedimento", ""),
            "descricao_procedimento": xml.get("descricao_procedimento", ""),
            "codigo_glosa": xml.get("tipo_glosa", ""),
            "linha_foco": focus_by_code.get(str(xml.get("tipo_glosa", "")), "FORA_DO_FOCO"),
            "valor_informado": xml.get("valor_informado", ""),
            "valor_glosa": xml.get("valor_glosa", ""),
            "origem_mv": oracle.get("origem_tabela", ""),
            "decisao": decision.get("decisao", "AGUARDAR_DOCUMENTACAO"),
            "valor_recursado": decision.get("valor_recursado", "0.00"),
            "justificativa": decision.get("justificativa", ""),
            "confirmacao_manual_provavel": "S" if decision.get("confirmacao_manual_provavel") else "N",
        })
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def build_checklist(
    definitions: dict,
    auth_store: AuthStore,
    contract: dict,
    decisions: dict,
    glossary: dict,
    xsd_path: Path | None,
    xml_path: Path,
) -> dict:
    """Combina verificacoes automaticas com as confirmacoes humanas persistidas."""
    focus_codes = {str(item.get("codigo")) for item in glossary.get("catalogo_foco", [])}
    contract_items = contract.get("itens", [])
    automatic = {
        "auth_configured": auth_store.configured(),
        "individual_users": len([user for user in auth_store.list_users() if user["active"]]) >= 3,
        "contract_loaded": bool(contract_items),
        "focus_items": any(str((item.get("xml") or {}).get("tipo_glosa", "")) in focus_codes for item in contract_items),
        "glossary_ready": len(focus_codes) >= 64,
        "guides_confirmed": bool(decisions.get("cabecalho", {}).get("guias_confirmadas_manualmente")),
        "appeal_selected": any(item.get("decisao") == "RECORRER" for item in decisions.get("itens", [])),
        "xsd_available": bool(xsd_path and xsd_path.exists()),
        "xml_dry_run": xml_path.exists(),
    }
    saved = auth_store.checklist_state()
    stages: dict[str, list[dict]] = {}
    completed = 0
    all_items = definitions.get("items", [])
    for definition in all_items:
        item = dict(definition)
        state = saved.get(item["id"], {})
        item["checked"] = bool(automatic.get(item["id"], state.get("checked", False)))
        item["checked_by"] = state.get("checked_by")
        item["checked_at"] = state.get("checked_at")
        completed += int(item["checked"])
        stages.setdefault(item["stage"], []).append(item)
    return {
        "ok": True,
        "completed": completed,
        "total": len(all_items),
        "percent": round((completed / len(all_items)) * 100) if all_items else 0,
        "stages": [{"name": name, "items": items} for name, items in stages.items()],
    }


def import_xml_payload(
    payload: bytes,
    contract_path: Path,
    decisions_path: Path,
    oracle_dump_dir: Path,
    imported_by: str,
    xml_path: Path | None = None,
) -> dict:
    """Concilia um demonstrativo, arquiva o estado atual e inicia uma nova analise."""
    if not payload.strip():
        raise ValidationError("O arquivo XML esta vazio.")
    lowered = payload[:100_000].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValidationError("XML com DTD ou entidades nao e permitido.")
    descriptor, temporary_name = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        try:
            contract = build_contract(Path(temporary_name), oracle_dump_dir)
        except FileNotFoundError as exc:
            missing = Path(exc.filename).name if exc.filename else "snapshot da guia"
            raise ValidationError(
                f"Nao existe snapshot MV local para conciliar esta guia ({missing}). "
                "Solicite a extracao somente leitura antes de importar."
            ) from exc
        except (ValueError, TypeError, ParseError) as exc:
            raise ValidationError(str(exc)) from exc
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir = contract_path.parent / "archive" / timestamp
    if contract_path.exists():
        atomic_write(archive_dir / contract_path.name, contract_path.read_bytes())
    if decisions_path.exists():
        atomic_write(archive_dir / decisions_path.name, decisions_path.read_bytes())
    if xml_path and xml_path.exists():
        atomic_write(archive_dir / xml_path.name, xml_path.read_bytes())
        xml_path.unlink()
    contract["_importacao"] = {"data_hora": datetime.now().isoformat(timespec="seconds"), "usuario": imported_by}
    decisions = decision_template(contract)
    atomic_write(contract_path, json.dumps(contract, ensure_ascii=False, indent=2).encode("utf-8"))
    atomic_write(decisions_path, json.dumps(decisions, ensure_ascii=False, indent=2).encode("utf-8"))
    return {"ok": True, "protocolo": contract["protocolo"], "resumo": contract["resumo"], "archive": str(archive_dir)}


def make_handler(
    contract_path: Path,
    decisions_path: Path,
    xml_path: Path,
    registry: Path,
    panel_path: Path,
    xsd_path: Path | None,
    glossary_path: Path,
    login_path: Path,
    logo_path: Path,
    checklist_path: Path,
    auth_store: AuthStore,
    oracle_dump_dir: Path,
):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, value: object, headers: dict[str, str] | None = None) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, header_value in (headers or {}).items():
                self.send_header(name, header_value)
            self.end_headers()
            self.wfile.write(body)

        def _page(self, path: Path) -> None:
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, location: str) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _token(self) -> str | None:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            morsel = cookie.get("nexo_session")
            return morsel.value if morsel else None

        def _user(self) -> dict | None:
            return auth_store.user_for_token(self._token())

        @staticmethod
        def _session_cookie(token: str) -> str:
            return f"nexo_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}"

        @staticmethod
        def _expired_cookie() -> str:
            return "nexo_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"

        def _same_origin(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            return urlparse(origin).netloc == self.headers.get("Host", "")

        def _require_user(self) -> dict | None:
            user = self._user()
            if not user:
                self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Sessao expirada. Entre novamente."})
            return user

        def _file(self, body: bytes, content_type: str, filename: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 2_000_000:
                raise ValidationError("Payload excede 2 MB.")
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValidationError("JSON invalido.") from exc
            if not isinstance(value, dict):
                raise ValidationError("O payload deve ser um objeto JSON.")
            return value

        def _raw_body(self, limit: int = 5_000_000) -> bytes:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValidationError("Tamanho do arquivo invalido.") from exc
            if length <= 0:
                raise ValidationError("Selecione um arquivo XML.")
            if length > limit:
                raise ValidationError("O XML excede o limite de 5 MB.")
            return self.rfile.read(length)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                if path == "/api/health":
                    self._json(HTTPStatus.OK, {"ok": True})
                    return
                if path == "/api/auth/status":
                    user = self._user()
                    self._json(HTTPStatus.OK, {"ok": True, "configured": auth_store.configured(), "authenticated": bool(user), "user": user})
                    return
                if path == "/login":
                    if self._user():
                        self._redirect("/")
                    else:
                        self._page(login_path)
                    return
                if path in {"/assets/logo-beneficente.png", "/assets/logo-beneficente-v2.png"}:
                    asset_path = logo_path if path.endswith("logo-beneficente.png") else logo_path.with_name("logo-beneficente-v2.png")
                    body = asset_path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                user = self._user()
                if not user:
                    if path in {"/", "/index.html"}:
                        self._redirect("/login")
                    else:
                        self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Sessao expirada. Entre novamente."})
                    return
                if path == "/api/contract":
                    self._json(HTTPStatus.OK, load_json(contract_path))
                elif path == "/api/decisions":
                    contract = load_json(contract_path)
                    value = load_json(decisions_path) if decisions_path.exists() else decision_template(contract)
                    self._json(HTTPStatus.OK, value)
                elif path == "/api/status":
                    contract = load_json(contract_path)
                    has_mv_snapshot = any(item.get("oracle") for item in contract.get("itens", []))
                    self._json(HTTPStatus.OK, {
                        "ok": True,
                        "data_source": "SNAPSHOT_MV" if has_mv_snapshot else "ARQUIVO_TISS",
                        "oracle_write_enabled": False,
                        "xsd_available": bool(xsd_path and xsd_path.exists()),
                        "xml_generated": xml_path.exists(),
                        "bi_export_available": True,
                        "glossary_available": glossary_path.exists(),
                    })
                elif path == "/api/glossary":
                    self._json(HTTPStatus.OK, load_json(glossary_path))
                elif path == "/api/checklist":
                    contract = load_json(contract_path)
                    decisions = load_json(decisions_path) if decisions_path.exists() else decision_template(contract)
                    self._json(HTTPStatus.OK, build_checklist(
                        load_json(checklist_path), auth_store, contract, decisions,
                        load_json(glossary_path), xsd_path, xml_path,
                    ))
                elif path == "/api/users":
                    if user["role"] != "admin":
                        self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Apenas administradores gerenciam acessos."})
                    else:
                        self._json(HTTPStatus.OK, {"ok": True, "users": auth_store.list_users()})
                elif path == "/api/export/bi.csv":
                    contract = load_json(contract_path)
                    decisions = load_json(decisions_path) if decisions_path.exists() else decision_template(contract)
                    glossary = load_json(glossary_path)
                    protocol = contract.get("protocolo", {}).get("numero_protocolo", "glosas")
                    self._file(
                        build_bi_csv(contract, decisions, glossary),
                        "text/csv; charset=utf-8",
                        f"glosas_{protocol}_bi.csv",
                    )
                elif path == "/api/download/xml":
                    if not xml_path.exists():
                        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Gere e valide o XML antes de baixar."})
                    else:
                        self._file(xml_path.read_bytes(), "application/xml", xml_path.name)
                elif path == "/api/download/decisions":
                    contract = load_json(contract_path)
                    value = load_json(decisions_path) if decisions_path.exists() else decision_template(contract)
                    body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
                    self._file(body, "application/json; charset=utf-8", "decisoes_recurso.json")
                elif path in {"/", "/index.html"}:
                    self._page(panel_path)
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except ValidationError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            try:
                if not self._same_origin():
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Origem da requisicao nao permitida."})
                    return
                path = urlparse(self.path).path
                if path == "/api/import/xml":
                    user = self._require_user()
                    if not user:
                        return
                    content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if content_type not in {"application/xml", "text/xml", "application/octet-stream"}:
                        raise ValidationError("Formato invalido. Selecione um arquivo .xml.")
                    result = import_xml_payload(
                        self._raw_body(), contract_path, decisions_path, oracle_dump_dir, user["display_name"], xml_path
                    )
                    self._json(HTTPStatus.OK, result)
                    return
                value = self._body()
                if path == "/api/auth/setup":
                    user = auth_store.create_initial_admin(value.get("username"), value.get("display_name"), value.get("password"))
                    token = auth_store.create_session(user["id"])
                    self._json(HTTPStatus.CREATED, {"ok": True, "user": user}, {"Set-Cookie": self._session_cookie(token)})
                    return
                if path == "/api/auth/login":
                    user = auth_store.authenticate(value.get("username"), value.get("password"))
                    if not user:
                        self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Usuario ou senha invalidos."})
                        return
                    token = auth_store.create_session(user["id"])
                    self._json(HTTPStatus.OK, {"ok": True, "user": user}, {"Set-Cookie": self._session_cookie(token)})
                    return
                user = self._require_user()
                if not user:
                    return
                if path == "/api/auth/logout":
                    auth_store.revoke_session(self._token())
                    self._json(HTTPStatus.OK, {"ok": True}, {"Set-Cookie": self._expired_cookie()})
                elif path == "/api/users":
                    if user["role"] != "admin":
                        self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Apenas administradores gerenciam acessos."})
                    else:
                        created = auth_store.create_user(value.get("username"), value.get("display_name"), value.get("password"), str(value.get("role", "analyst")))
                        self._json(HTTPStatus.CREATED, {"ok": True, "user": created})
                elif path == "/api/checklist":
                    definitions = load_json(checklist_path)
                    manual_ids = {item["id"] for item in definitions.get("items", []) if item.get("kind") == "manual"}
                    item_id = str(value.get("item_id", ""))
                    if item_id not in manual_ids:
                        raise ValidationError("Somente itens manuais da checklist podem ser alterados.")
                    auth_store.set_checklist(item_id, bool(value.get("checked")), int(user["id"]))
                    self._json(HTTPStatus.OK, {"ok": True})
                elif path == "/api/decisions":
                    # A validacao completa ocorre na geracao; salvar rascunho e deliberadamente permitido.
                    atomic_write(decisions_path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
                    self._json(HTTPStatus.OK, {"ok": True, "path": str(decisions_path)})
                elif path == "/api/generate":
                    contract = load_json(contract_path)
                    payload, warnings = generate_xml(contract, value, registry)
                    if xsd_path and xsd_path.exists():
                        validate_xsd_payload(payload, xsd_path)
                    else:
                        warnings.append(f"Validacao XSD nao executada; schema nao encontrado em {xsd_path}.")
                    atomic_write(decisions_path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
                    atomic_write(xml_path, payload)
                    self._json(HTTPStatus.OK, {"ok": True, "path": str(xml_path), "warnings": warnings})
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
            except (ValidationError, AuthError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            except OSError as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            print(f"[painel] {self.address_string()} - {format % args}")

    return Handler


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Permite escutar fora do loopback. Use somente em rede confiavel ou dentro de container.",
    )
    parser.add_argument("--auth-db", type=Path, default=root / "output" / "nexo_auth.sqlite3")
    parser.add_argument("--checklist", type=Path, default=root / "resources" / "mvp_checklist.json")
    parser.add_argument("--oracle-dump-dir", type=Path, default=root / "data" / "oracle_dump")
    parser.add_argument("--contract", type=Path, default=root / "output" / "glosa_reconciliation.json")
    parser.add_argument("--decisions", type=Path, default=root / "output" / "decisoes_recurso.json")
    parser.add_argument("--xml-out", type=Path, default=root / "output" / "recurso_glosa.xml")
    parser.add_argument("--registry", type=Path, default=root / "output" / "submission_registry.sqlite3")
    parser.add_argument(
        "--glossary",
        type=Path,
        default=root / "resources" / "glosa_dictionary.json",
        help="Dicionario operacional local dos codigos de glosa.",
    )
    parser.add_argument(
        "--xsd",
        type=Path,
        default=root / "xsd" / "tiss_v4_03_00" / "tissV4_03_00.xsd",
        help="Schema TISS oficial da ANS (o XML declara Padrao 4.01.00; a ANS so disponibiliza "
        "para download a versao vigente, 4.03.00 - validou limpo contra o caso real ate agora).",
    )
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_network:
        print(
            "ERRO: por seguranca use --allow-network explicitamente para escutar fora do computador local.",
            file=sys.stderr,
        )
        return 2
    panel_path = root / "web" / "panel.html"
    login_path = root / "web" / "login.html"
    logo_path = root / "web" / "assets" / "logo-beneficente.png"
    auth_store = AuthStore(args.auth_db)
    handler = make_handler(
        args.contract,
        args.decisions,
        args.xml_out,
        args.registry,
        panel_path,
        args.xsd,
        args.glossary,
        login_path,
        logo_path,
        args.checklist,
        auth_store,
        args.oracle_dump_dir,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Painel local: http://{args.host}:{args.port}")
    print("Ctrl+C para encerrar. Nenhum envio ao Portal Protheus e realizado.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
