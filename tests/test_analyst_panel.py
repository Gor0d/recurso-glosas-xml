from __future__ import annotations

import csv
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyst_panel import build_bi_csv  # noqa: E402
from recurso_glosa import weighted_length  # noqa: E402


class BiExportTests(unittest.TestCase):
    def test_export_flattens_contract_and_decision(self) -> None:
        contract = {
            "protocolo": {"numero_protocolo": "00123", "numero_guia_prestador": "99"},
            "itens": [{
                "sequencialItem": 7,
                "status": "CONFIRMADO",
                "motivo": "match",
                "xml": {"codigo_procedimento": "ABC", "valor_glosa": "12.30"},
                "oracle": {"origem_tabela": "TISS_ITGUIA"},
            }],
        }
        decisions = {"itens": [{
            "sequencialItem": 7,
            "decisao": "RECORRER",
            "valor_recursado": "10.00",
            "justificativa": "Cobrança correta",
            "confirmacao_manual_provavel": True,
        }]}

        payload = build_bi_csv(contract, decisions).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(payload), delimiter=";"))

        self.assertEqual("00123", rows[0]["numero_protocolo"])
        self.assertEqual("RECORRER", rows[0]["decisao"])
        self.assertEqual("10.00", rows[0]["valor_recursado"])
        self.assertEqual("S", rows[0]["confirmacao_manual_provavel"])


class GlossaryTests(unittest.TestCase):
    def test_glossary_covers_every_code_in_pilot_contract(self) -> None:
        glossary = json.loads((ROOT / "resources" / "glosa_dictionary.json").read_text(encoding="utf-8"))
        contract = json.loads((ROOT / "output" / "glosa_reconciliation.json").read_text(encoding="utf-8"))
        catalog = {item["codigo"]: item for item in glossary["codigos"]}
        used_codes = {str(item["xml"]["tipo_glosa"]) for item in contract["itens"]}

        self.assertEqual(set(), used_codes - set(catalog))
        for code in used_codes:
            entry = catalog[code]
            self.assertTrue(entry["grupo"])
            self.assertTrue(entry["descricao"])
            self.assertTrue(entry["conferir"])
            self.assertTrue(entry["documentos"])
            self.assertLessEqual(weighted_length(entry["texto_base"]), 150)

    def test_focus_catalog_has_expected_business_lines(self) -> None:
        glossary = json.loads((ROOT / "resources" / "glosa_dictionary.json").read_text(encoding="utf-8"))
        counts: dict[str, int] = {}
        for item in glossary["catalogo_foco"]:
            counts[item["linha"]] = counts.get(item["linha"], 0) + 1

        self.assertEqual({"HONORARIOS": 10, "OPME": 12, "DIARIAS": 17, "TAXAS": 25}, counts)
        self.assertEqual(64, len(glossary["catalogo_foco"]))
        for line in glossary["linhas_foco"]:
            self.assertLessEqual(weighted_length(line["texto_base"]), 150)


if __name__ == "__main__":
    unittest.main()
