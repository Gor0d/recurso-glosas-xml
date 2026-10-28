import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyst_panel import build_checklist  # noqa: E402
from auth import AuthError, AuthStore  # noqa: E402


def test_first_admin_authentication_and_session(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    assert not store.configured()

    admin = store.create_initial_admin("gestor", "Gestor Local", "senha-forte-123")
    assert store.configured()
    assert admin["role"] == "admin"
    assert store.authenticate("gestor", "senha-invalida") is None
    assert store.authenticate("GESTOR", "senha-forte-123")["id"] == admin["id"]

    token = store.create_session(admin["id"])
    assert store.user_for_token(token)["username"] == "gestor"
    store.revoke_session(token)
    assert store.user_for_token(token) is None


def test_only_one_initial_admin_and_individual_users(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.create_initial_admin("gestor", "Gestor Local", "senha-forte-123")
    with pytest.raises(AuthError, match="ja foi configurado"):
        store.create_initial_admin("outro", "Outro Gestor", "senha-forte-456")

    store.create_user("paula", "Paula Teste", "senha-paula-123", "analyst")
    store.create_user("joyce", "Joyce Teste", "senha-joyce-123", "analyst")
    assert {user["username"] for user in store.list_users()} == {"gestor", "paula", "joyce"}


def test_checklist_combines_automatic_and_manual_state(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    admin = store.create_initial_admin("gestor", "Gestor Local", "senha-forte-123")
    store.set_checklist("roles_reviewed", True, admin["id"])
    definitions = json.loads((ROOT / "resources" / "mvp_checklist.json").read_text(encoding="utf-8"))
    glossary = json.loads((ROOT / "resources" / "glosa_dictionary.json").read_text(encoding="utf-8"))
    focus_code = glossary["catalogo_foco"][0]["codigo"]
    contract = {"itens": [{"xml": {"tipo_glosa": focus_code}}]}
    decisions = {"cabecalho": {"guias_confirmadas_manualmente": True}, "itens": [{"decisao": "RECORRER"}]}
    xsd = tmp_path / "schema.xsd"
    xml = tmp_path / "recurso.xml"
    xsd.write_text("x", encoding="utf-8")
    xml.write_text("x", encoding="utf-8")

    result = build_checklist(definitions, store, contract, decisions, glossary, xsd, xml)
    items = {item["id"]: item for stage in result["stages"] for item in stage["items"]}
    assert items["auth_configured"]["checked"] is True
    assert items["focus_items"]["checked"] is True
    assert items["roles_reviewed"]["checked"] is True
    assert items["roles_reviewed"]["checked_by"] == "Gestor Local"
    assert items["individual_users"]["checked"] is False
