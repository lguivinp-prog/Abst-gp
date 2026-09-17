import unittest
from unittest.mock import patch, MagicMock
import os
import requests
from app.services.v6.integrations.providers.sunat_adapter import SUNATProvider
from app.services.v6.integrations.providers.sunat_activities_provider import SunatActivitiesProvider
from app.services.v6.integrations.providers.ciiu_adapter import CIIUProvider
from app.services.v6.integrations.validation_orchestrator import SupplierValidationOrchestrator
from app.models.v6.ciiu_catalog import CiiuCatalog
from app.models.v6.supplier import Supplier

class TestSUNATProvider(unittest.TestCase):
    def test_a_200_activo_habido_ruc_correcto(self):
        provider = SUNATProvider()
        with patch('app.services.v6.integrations.providers.sunat_adapter.requests.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "numero_documento": "1041", "razon_social": "Test", "estado": "ACTIVO", "condicion": "HABIDO"
            }
            mock_get.return_value = mock_resp
            with patch.dict(os.environ, {"DECOLECTA_API_TOKEN": "test-token"}):
                res = provider.validate("1041")
            self.assertEqual(res.status, "PASSED")

class TestSunatActivitiesProvider(unittest.TestCase):
    def test_migo_missing_token(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = SunatActivitiesProvider()
            res = provider.validate("1041")
            self.assertEqual(res.status, "MANUAL_REQUIRED")
            self.assertFalse(res.payload["activities_complete"])

    @patch('app.services.v6.integrations.providers.sunat_activities_provider.requests.get')
    def test_migo_success_3_activities_normalization(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True, "ruc": "1041",
            "actividades_economicas": [
                "Principal - 4659 - VENTA AL POR MAYOR",
                "Secundaria 1 - 5610 - ACTIVIDADES DE RESTAURANTES",
                "Secundaria 2 - OTRA ACTIVIDAD SIN CODIGO"
            ]
        }
        mock_get.return_value = mock_resp
        provider = SunatActivitiesProvider()
        with patch.dict(os.environ, {"MIGO_API_TOKEN": "test-token"}):
            res = provider.validate("1041")
        self.assertEqual(res.status, "PASSED")
        self.assertTrue(res.payload["activities_complete"])
        self.assertEqual(res.payload["activities_count"], 3)
        self.assertEqual(res.payload["activities"][0]["codigo_reportado"], "4659")
        self.assertEqual(res.payload["activities"][0]["descripcion_sunat"], "VENTA AL POR MAYOR")
        self.assertEqual(res.payload["activities"][1]["codigo_reportado"], "5610")
        self.assertEqual(res.payload["activities"][1]["descripcion_sunat"], "ACTIVIDADES DE RESTAURANTES")
        self.assertEqual(res.payload["activities"][2]["codigo_reportado"], None)
        self.assertEqual(res.payload["activities"][2]["descripcion_sunat"], "OTRA ACTIVIDAD SIN CODIGO")

    @patch('app.services.v6.integrations.providers.sunat_activities_provider.requests.get')
    def test_migo_success_1_activity(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True, "ruc": "1041",
            "actividades_economicas": ["Act1"]
        }
        mock_get.return_value = mock_resp
        provider = SunatActivitiesProvider()
        with patch.dict(os.environ, {"MIGO_API_TOKEN": "test-token"}):
            res = provider.validate("1041")
        self.assertEqual(res.status, "PASSED")
        self.assertTrue(res.payload["activities_complete"])
        self.assertEqual(res.payload["activities_count"], 1)

    @patch('app.services.v6.integrations.providers.sunat_activities_provider.requests.get')
    def test_migo_mismatch_ruc(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True, "ruc": "9999", "actividades_economicas": ["Act1"]
        }
        mock_get.return_value = mock_resp
        provider = SunatActivitiesProvider()
        with patch.dict(os.environ, {"MIGO_API_TOKEN": "test-token"}):
            res = provider.validate("1041")
        self.assertEqual(res.status, "REVIEW_REQUIRED")
        self.assertFalse(res.payload["activities_complete"])

    @patch('app.services.v6.integrations.providers.sunat_activities_provider.requests.get')
    def test_migo_empty_activities(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True, "ruc": "1041", "actividades_economicas": []
        }
        mock_get.return_value = mock_resp
        provider = SunatActivitiesProvider()
        with patch.dict(os.environ, {"MIGO_API_TOKEN": "test-token"}):
            res = provider.validate("1041")
        self.assertEqual(res.status, "MANUAL_REQUIRED")
        self.assertFalse(res.payload["activities_complete"])
        self.assertEqual(res.payload["activities_count"], 0)

class TestCIIUProvider(unittest.TestCase):
    def test_catalog_incomplete(self):
        provider = CIIUProvider()
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [CiiuCatalog()] # 1 item
        res = provider.validate(mock_db, [{"descripcion_sunat": "Act1", "tipo": "PRINCIPAL"}], True, "")
        self.assertEqual(res.status, "REVIEW_REQUIRED")

    def test_exact_code_parsing(self):
        provider = CIIUProvider()
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [MagicMock()] * 419
        catalog = mock_db.query.return_value.all.return_value
        catalog[0].codigo = "4741"
        catalog[0].descripcion = "Desc"

        # mock requests inside _get_inei_detail
        with patch('app.services.v6.integrations.providers.ciiu_adapter.requests.get') as mock_get:
            mock_get.return_value = MagicMock(status_code=404)
            res = provider.validate(mock_db, [{"descripcion_sunat": "4741 - VENTA", "tipo": "PRINCIPAL"}], True, "")
        self.assertEqual(res.status, "PASSED")

class TestCIIUProviderINEI(unittest.TestCase):
    @patch('app.services.v6.integrations.providers.ciiu_adapter.requests.get')
    def test_inei_html_extraction(self, mock_get):
        html_content = """
        <table cellpadding='1' cellspacing='1' border='1' bordercolor='#3C7EB1'>
            <tr><td bgcolor='#3C7EB1'><a class='popup'>CIIU4</a></td><td bgcolor='#3C7EB1'><a class='popup'>Descripción</a></td><td bgcolor='#3C7EB1'><a class='popup'>Incluye</a></td><td bgcolor='#3C7EB1'><a class='popup'>No Incluye</a></td></tr>
            <tr><td><a class='contenido'>5610</a></td><td><a class='contenido'>Actividades de restaurantes y de servicio móvil de comidas</a></td><td><a class='contenido'>Esta clase comprende el servicio de comidas a los clientes. Se incluyen también las actividades de restaurantes.</a></td><td><a class='contenido'>No se incluye la explotación de instalaciones.</a></td></tr>
        </table>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html_content
        mock_get.return_value = mock_resp

        provider = CIIUProvider()
        res = provider._get_inei_detail("5610")

        self.assertTrue(res["detail_retrieved"])
        self.assertEqual(res["incluye"], "Esta clase comprende el servicio de comidas a los clientes. Se incluyen también las actividades de restaurantes.")
        self.assertEqual(res["no_incluye"], "No se incluye la explotación de instalaciones.")

    @patch('app.services.v6.integrations.providers.ciiu_adapter.requests.get')
    def test_inei_missing_no_incluye(self, mock_get):
        html_content = """
        <table cellpadding='1' cellspacing='1' border='1' bordercolor='#3C7EB1'>
            <tr><td bgcolor='#3C7EB1'><a class='popup'>CIIU4</a></td><td bgcolor='#3C7EB1'><a class='popup'>Descripción</a></td><td bgcolor='#3C7EB1'><a class='popup'>Incluye</a></td></tr>
            <tr><td><a class='contenido'>1234</a></td><td><a class='contenido'>Test Desc</a></td><td><a class='contenido'>Incluye algo.</a></td></tr>
        </table>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html_content
        mock_get.return_value = mock_resp

        provider = CIIUProvider()
        res = provider._get_inei_detail("1234")

        self.assertTrue(res["detail_retrieved"])
        self.assertEqual(res["incluye"], "Incluye algo.")
        self.assertIsNone(res["no_incluye"])

    @patch('app.services.v6.integrations.providers.ciiu_adapter.requests.get')
    def test_inei_different_order(self, mock_get):
        html_content = """
        <table cellpadding='1' cellspacing='1' border='1' bordercolor='#3C7EB1'>
            <tr><td bgcolor='#3C7EB1'><a class='popup'>No Incluye</a></td><td bgcolor='#3C7EB1'><a class='popup'>CIIU4</a></td><td bgcolor='#3C7EB1'><a class='popup'>Incluye</a></td><td bgcolor='#3C7EB1'><a class='popup'>Descripción</a></td></tr>
            <tr><td><a class='contenido'>No incluye esto.</a></td><td><a class='contenido'>1234</a></td><td><a class='contenido'>Incluye esto.</a></td><td><a class='contenido'>Desc</a></td></tr>
        </table>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html_content
        mock_get.return_value = mock_resp

        provider = CIIUProvider()
        res = provider._get_inei_detail("1234")

        self.assertTrue(res["detail_retrieved"])
        self.assertEqual(res["incluye"], "Incluye esto.")
        self.assertEqual(res["no_incluye"], "No incluye esto.")

    @patch('app.services.v6.integrations.providers.ciiu_adapter.requests.get')
    def test_inei_timeout(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.Timeout

        provider = CIIUProvider()

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [MagicMock()] * 419
        catalog = mock_db.query.return_value.all.return_value
        catalog[0].codigo = "4741"
        catalog[0].descripcion = "Desc"

        res = provider.validate(mock_db, [{"descripcion_sunat": "4741 - VENTA", "tipo": "PRINCIPAL"}], True, "")

        self.assertEqual(res.status, "PASSED")
        # Ensure classification is still verified but detail is false
        self.assertTrue(res.payload["results"][0]["classification_verified"])
        self.assertFalse(res.payload["results"][0]["detail_retrieved"])
        self.assertEqual(res.payload["results"][0]["detail_status"], "UNAVAILABLE")

    @patch('app.services.v6.integrations.providers.ciiu_adapter.requests.get')
    def test_inei_html_with_br_and_entities(self, mock_get):
        html_content = """
        <table cellpadding='1' cellspacing='1' border='1' bordercolor='#3C7EB1'>
            <tr><td bgcolor='#3C7EB1'><a class='popup'>Incluye</a></td></tr>
            <tr><td><a class='contenido'>Hola<br>Mundo &amp; Todos</a></td></tr>
        </table>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html_content
        mock_get.return_value = mock_resp

        provider = CIIUProvider()
        res = provider._get_inei_detail("1234")

        self.assertTrue(res["detail_retrieved"])
        self.assertEqual(res["incluye"], "Hola Mundo & Todos")

class TestOrchestrator(unittest.TestCase):
    def test_migo_principal_detection(self):
        orch = SupplierValidationOrchestrator()
        orch.sunat.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"actividad_economica": "VENTA DE ZAPATOS"}))
        orch.sunat_activities.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"activities_complete": True, "activities": [{"descripcion_sunat": "VENTA AL POR MAYOR", "tipo": "PRINCIPAL", "orden": 1}, {"descripcion_sunat": "VENTA DE ZAPATOS", "tipo": "SECUNDARIA", "orden": 2}, {"descripcion_sunat": "OTROS", "tipo": "SECUNDARIA", "orden": 3}]}))
        orch.rnp.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.fup.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.ciiu.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"codigo_ciiu": "0000"}))

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = Supplier(ruc="1041")

        orch.run_async_validation(mock_db, 1, 1)

        sunat_call = orch.sunat.validate.call_args
        self.assertEqual(sunat_call[0][0], "1041")
        self.assertEqual(mock_db.add.call_count, 5)

    def test_migo_ambiguous_principal(self):
        orch = SupplierValidationOrchestrator()
        orch.sunat.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"actividad_economica": "VENTA DE ZAPATOS"}))
        orch.sunat_activities.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"activities_complete": True, "activities": [{"descripcion_sunat": "VENTA DE ZAPATOS", "tipo": "SECUNDARIA", "orden": 1}, {"descripcion_sunat": "VENTA DE ZAPATOS", "tipo": "SECUNDARIA", "orden": 2}, {"descripcion_sunat": "OTROS", "tipo": "SECUNDARIA", "orden": 3}]}))
        orch.rnp.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.fup.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.ciiu.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"codigo_ciiu": "0000"}))

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = Supplier(ruc="1041")

        orch.run_async_validation(mock_db, 1, 1)

        profile_add = mock_db.add.call_args_list[0]
        self.assertIsNotNone(profile_add)

    def test_ciiu_partial_failure(self):
        orch = SupplierValidationOrchestrator()
        orch.sunat.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"actividad_economica": "VENTA DE ZAPATOS"}))
        orch.sunat_activities.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"activities_complete": True, "activities": [{"descripcion_sunat": "ACT1", "tipo": "PRINCIPAL", "orden": 1}, {"descripcion_sunat": "ACT2", "tipo": "SECUNDARIA", "orden": 2}, {"descripcion_sunat": "ACT3", "tipo": "SECUNDARIA", "orden": 3}]}))
        orch.rnp.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.fup.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.ciiu.validate = MagicMock(return_value=MagicMock(status="REVIEW_REQUIRED", payload={"activities": [{"status": "PASSED"}, {"status": "MANUAL_REQUIRED"}, {"status": "PASSED"}]}))

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = Supplier(ruc="1041")

        orch.run_async_validation(mock_db, 1, 1)

        reqs = [call[0][0] for call in mock_db.add.call_args_list]
        ciiu_req = next((r for r in reqs if getattr(r, 'source', None) == "CIIU"), None)
        self.assertIsNotNone(ciiu_req)
        self.assertEqual(ciiu_req.status, "REVIEW_REQUIRED")
        self.assertEqual(len(ciiu_req.response_payload["activities"]), 3)

    def test_no_supplier_eligible_fields_in_results(self):
        orch = SupplierValidationOrchestrator()
        orch.sunat.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"actividad_economica": "VENTA DE ZAPATOS"}))
        orch.sunat_activities.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"activities_complete": True, "activities": [{"descripcion_sunat": "VENTA DE ZAPATOS", "tipo": "PRINCIPAL", "orden": 1}]}))
        orch.rnp.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.fup.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.ciiu.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"results": [{"codigo_ciiu": "0000", "detail_retrieved": True}]}))

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = Supplier(ruc="1041")

        orch.run_async_validation(mock_db, 1, 1)

        reqs = [call[0][0] for call in mock_db.add.call_args_list]
        ciiu_req = next((r for r in reqs if getattr(r, 'source', None) == "CIIU"), None)

        self.assertIsNotNone(ciiu_req)
        for res in ciiu_req.response_payload["results"]:
            self.assertNotIn("supplier_eligible", res)
            self.assertNotIn("cumple_objeto", res)

    def test_cross_source_consistency_match(self):
        orch = SupplierValidationOrchestrator()
        orch.sunat.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"actividad_reportada_decolecta": "VENTA DE ZAPATOS", "estado": "ACTIVO", "condicion": "HABIDO"}))
        orch.sunat_activities.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"activities_complete": True, "activities": [{"descripcion_sunat": "VENTA DE ZAPATOS", "tipo": "PRINCIPAL"}]}))
        orch.rnp.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.fup.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.ciiu.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"results": [{"codigo_ciiu": "0000"}]}))

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = Supplier(ruc="1041")

        orch.run_async_validation(mock_db, 1, 1)

        reqs = [call[0][0] for call in mock_db.add.call_args_list]
        migo_req = next((r for r in reqs if getattr(r, 'source', None) == "MIGO_ACTIVITIES"), None)

        self.assertIsNotNone(migo_req)
        self.assertTrue(migo_req.response_payload["cross_source_consistency"])
        self.assertEqual(migo_req.response_payload["cross_source_status"], "CONSISTENT")

    def test_cross_source_consistency_mismatch(self):
        orch = SupplierValidationOrchestrator()
        orch.sunat.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"actividad_reportada_decolecta": "OTRA COSA", "estado": "ACTIVO", "condicion": "HABIDO"}))
        orch.sunat_activities.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"activities_complete": True, "activities": [{"descripcion_sunat": "VENTA DE ZAPATOS", "tipo": "PRINCIPAL"}]}))
        orch.rnp.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.fup.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={}))
        orch.ciiu.validate = MagicMock(return_value=MagicMock(status="PASSED", payload={"results": [{"codigo_ciiu": "0000"}]}))

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = Supplier(ruc="1041")

        orch.run_async_validation(mock_db, 1, 1)

        reqs = [call[0][0] for call in mock_db.add.call_args_list]
        migo_req = next((r for r in reqs if getattr(r, 'source', None) == "MIGO_ACTIVITIES"), None)
        sunat_req = next((r for r in reqs if getattr(r, 'source', None) == "SUNAT"), None)

        self.assertIsNotNone(migo_req)
        self.assertFalse(migo_req.response_payload["cross_source_consistency"])
        self.assertEqual(migo_req.response_payload["cross_source_status"], "REVIEW_REQUIRED")
        self.assertEqual(migo_req.response_payload["cross_source_reason"], "ACTIVITY_SOURCE_MISMATCH")

        # C: mismatch NO degrada ACTIVO/HABIDO
        self.assertEqual(sunat_req.status, "PASSED")

        # D: mismatch NO añade cuarta actividad MIGO
        self.assertEqual(len(migo_req.response_payload["activities"]), 1)

if __name__ == '__main__':
    unittest.main()
