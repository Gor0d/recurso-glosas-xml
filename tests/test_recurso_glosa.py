from __future__ import annotations

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from recurso_glosa import (  # noqa: E402
    ANS_NS,
    ValidationError,
    calculate_hash,
    decision_template,
    generate_xml,
    mark_sent,
    validate_xsd,
    weighted_length,
)


def contract(status: str = "CONFIRMADO", description: str = "Material hospitalar") -> dict:
    return {
        "schema_version": "2.0",
        "protocolo": {
            "numero_lote_prestador": "9001",
            "numero_protocolo": "00000001",
            "numero_guia_prestador": "100000",
            "numero_guia_operadora": "0000000100000001",
            "registro_ans_operadora": "324477",
            "cnpj_prestador": "00000000000100",
            "padrao_tiss": "4.01.00",
        },
        "resumo": {"total_itens": 1, status: 1},
        "itens": [{
            "sequencialItem": 23,
            "status": status,
            "motivo": "fixture",
            "xml": {
                "sequencial_item": 23,
                "data_realizacao": "2026-05-11",
                "codigo_tabela": "19",
                "codigo_procedimento": "70222797",
                "descricao_procedimento": description,
                "valor_informado": "62.04",
                "valor_glosa": "62.04",
                "tipo_glosa": "2012",
            },
            "oracle": None,
        }],
    }


def decisions(source: dict, action: str = "RECORRER") -> dict:
    value = decision_template(source)
    value["gerado_em"] = "2026-09-08T10:30:00"
    value["cabecalho"].update({
        "sequencial_transacao": "32603",
        "numero_lote_recurso": "2396",
        "guias_confirmadas_manualmente": True,
    })
    value["itens"][0].update({
        "decisao": action,
        "valor_recursado": "62.04",
        "justificativa": "Cobranca conforme contrato",
    })
    return value


class ResourceGeneratorTests(unittest.TestCase):
    def test_generates_expected_xml_and_total(self):
        payload, warnings = generate_xml(contract(), decisions(contract()), None)
        self.assertFalse(warnings)
        self.assertTrue(payload.startswith(b"<?xml version='1.0' encoding='ISO-8859-1'?>"))
        root = ET.fromstring(payload)
        ns = {"a": ANS_NS}
        self.assertEqual(root.findtext(".//a:tipoTransacao", namespaces=ns), "RECURSO_GLOSA")
        self.assertEqual(root.findtext(".//a:sequencialItem", namespaces=ns), "0023")
        self.assertEqual(root.findtext(".//a:valorTotalRecursado", namespaces=ns), "62.04")
        self.assertEqual(root.findtext(".//a:hash", namespaces=ns), calculate_hash(root))

    def test_preserves_leading_zero_in_protocol(self):
        payload, _ = generate_xml(contract(), decisions(contract()), None)
        root = ET.fromstring(payload)
        self.assertEqual(root.findtext(f".//{{{ANS_NS}}}numeroProtocolo"), "00000001")

    def test_probable_requires_manual_confirmation(self):
        source = contract("PROVAVEL")
        with self.assertRaisesRegex(ValidationError, "confirmacao manual"):
            generate_xml(source, decisions(source), None)
        value = decisions(source)
        value["itens"][0]["confirmacao_manual_provavel"] = True
        generate_xml(source, value, None)

    def test_not_found_cannot_be_appealed(self):
        source = contract("NAO_LOCALIZADO")
        with self.assertRaisesRegex(ValidationError, "NAO_LOCALIZADO"):
            generate_xml(source, decisions(source), None)

    def test_guide_mapping_requires_explicit_confirmation(self):
        value = decisions(contract())
        value["cabecalho"]["guias_confirmadas_manualmente"] = False
        with self.assertRaisesRegex(ValidationError, "DE/PARA"):
            generate_xml(contract(), value, None)

    def test_resource_batch_must_differ(self):
        value = decisions(contract())
        value["cabecalho"]["numero_lote_recurso"] = "9001"
        with self.assertRaisesRegex(ValidationError, "lote original"):
            generate_xml(contract(), value, None)

    def test_value_cannot_exceed_glosa(self):
        value = decisions(contract())
        value["itens"][0]["valor_recursado"] = "62.05"
        with self.assertRaisesRegex(ValidationError, "no maximo"):
            generate_xml(contract(), value, None)

    def test_money_rejects_more_than_two_decimals(self):
        value = decisions(contract())
        value["itens"][0]["valor_recursado"] = "1.001"
        with self.assertRaisesRegex(ValidationError, "duas casas"):
            generate_xml(contract(), value, None)

    def test_changed_procedure_code_is_rejected(self):
        value = decisions(contract())
        value["itens"][0]["codigo_procedimento"] = "99999999"
        with self.assertRaisesRegex(ValidationError, "foi alterado"):
            generate_xml(contract(), value, None)

    def test_weighted_justification_limit(self):
        self.assertEqual(weighted_length("ABC 123"), 7)
        self.assertEqual(weighted_length("ação!"), 8)
        value = decisions(contract())
        value["itens"][0]["justificativa"] = "!" * 76
        with self.assertRaisesRegex(ValidationError, "152/150"):
            generate_xml(contract(), value, None)

    def test_non_latin1_is_rejected(self):
        value = decisions(contract())
        value["itens"][0]["justificativa"] = "Documento anexado 😀"
        with self.assertRaisesRegex(ValidationError, "ISO-8859-1"):
            generate_xml(contract(), value, None)

    def test_description_is_truncated_with_warning(self):
        source = contract(description="X" * 167)
        payload, warnings = generate_xml(source, decisions(source), None)
        self.assertEqual(len(ET.fromstring(payload).findtext(f".//{{{ANS_NS}}}descricaoProcedimento")), 150)
        self.assertIn("167", warnings[0])

    def test_all_contract_items_need_a_decision(self):
        value = decisions(contract())
        value["itens"] = []
        with self.assertRaisesRegex(ValidationError, "Faltam decisoes"):
            generate_xml(contract(), value, None)

    def test_no_appeal_item_is_rejected(self):
        value = decisions(contract(), "ACEITAR_GLOSA")
        with self.assertRaisesRegex(ValidationError, "Nenhum item"):
            generate_xml(contract(), value, None)

    def test_sent_protocol_blocks_new_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "resource.xml"
            registry = Path(tmp) / "registry.sqlite3"
            xml.write_bytes(generate_xml(contract(), decisions(contract()), registry)[0])
            mark_sent(registry, "00000001", xml)
            with self.assertRaisesRegex(ValidationError, "ja foi marcado"):
                generate_xml(contract(), decisions(contract()), registry)

    @unittest.skipUnless(os.environ.get("TISS_401_XSD"), "defina TISS_401_XSD para teste oficial")
    def test_official_xsd(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "resource.xml"
            xml.write_bytes(generate_xml(contract(), decisions(contract()), None)[0])
            validate_xsd(xml, Path(os.environ["TISS_401_XSD"]))


if __name__ == "__main__":
    unittest.main()
