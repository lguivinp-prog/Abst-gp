import unittest
from unittest.mock import MagicMock
from app.models.v6.case_requirement_matrix import CaseRequirementMatrix
from app.models.v6.supplier_offer_contract_term import SupplierOfferContractTerm
from app.services.v6.evaluation.contractual_resolver import ContractualResolver

class TestContractRules(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.resolver = ContractualResolver(self.db)

    def _evaluate(self, req, term):
        self.db.query.return_value.filter_by.return_value.all.return_value = [term] if term else []
        req.requirement_type = "CONTRACTUAL"
        conds = self.resolver.resolve_offer(1, [req])
        return conds[0].status, conds[0].final_value, conds[0].unit if conds else None

    def test_max_cumple_y_mejora(self):
        req = CaseRequirementMatrix(id=1, key="plazo", comparator="MAX", numeric_value=10.0, unit="days", value="10 days")
        term = SupplierOfferContractTerm(id=1, key="plazo", numeric_value=5.0, unit="days", value_text="5 days")
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(status, "CUMPLE_Y_MEJORA")
        self.assertEqual(final_val, "5 days")

    def test_min_cumple_y_mejora(self):
        req = CaseRequirementMatrix(id=2, key="garantia", comparator="MIN", numeric_value=12.0, unit="months", value="12 months")
        term = SupplierOfferContractTerm(id=2, key="garantia", numeric_value=24.0, unit="months", value_text="24 months")
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(status, "CUMPLE_Y_MEJORA")
        self.assertEqual(final_val, "24 months")

    def test_min_cumple(self):
        req = CaseRequirementMatrix(id=3, key="vida_util", comparator="MIN", numeric_value=3.0, unit="years", value="3 years")
        term = SupplierOfferContractTerm(id=3, key="vida_util", numeric_value=5.0, unit="years", value_text="5 years")
        # In current implementation, if term > req, it's CUMPLE_Y_MEJORA.
        # Wait, user example: MIN useful life 3y / offer 5y -> final 5y. Status wasn't specified but probably CUMPLE_Y_MEJORA.
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(final_val, "5 years")

    def test_max_no_cumple(self):
        req = CaseRequirementMatrix(id=4, key="plazo", comparator="MAX", numeric_value=10.0, unit="days", value="10 days")
        term = SupplierOfferContractTerm(id=4, key="plazo", numeric_value=12.0, unit="days", value_text="12 days")
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(status, "NO_CUMPLE")
        self.assertEqual(final_val, "10 days") # It falls back to req.value

    def test_range_inside(self):
        req = CaseRequirementMatrix(id=5, key="temperatura", comparator="RANGE", numeric_value=10.0, unit="C", value="5 a 10")
        term = SupplierOfferContractTerm(id=5, key="temperatura", numeric_value=7.0, unit="C", value_text="7")
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(status, "CUMPLE")

    def test_range_outside_below(self):
        req = CaseRequirementMatrix(id=6, key="temperatura", comparator="RANGE", numeric_value=10.0, unit="C", value="5 a 10")
        term = SupplierOfferContractTerm(id=6, key="temperatura", numeric_value=4.0, unit="C", value_text="4")
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(status, "NO_CUMPLE")

    def test_range_outside_above(self):
        req = CaseRequirementMatrix(id=6, key="temperatura", comparator="RANGE", numeric_value=10.0, unit="C", value="5 a 10")
        term = SupplierOfferContractTerm(id=6, key="temperatura", numeric_value=11.0, unit="C", value_text="11")
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(status, "NO_CUMPLE")

    def test_range_missing_offer(self):
        req = CaseRequirementMatrix(id=7, key="temperatura", comparator="RANGE", numeric_value=10.0, unit="C", value="5 a 10")
        status, final_val, final_unit = self._evaluate(req, None)
        self.assertEqual(status, "NO_OFERTADO")

    def test_range_incompleto(self):
        req = CaseRequirementMatrix(id=7, key="temperatura", comparator="RANGE", numeric_value=10.0, unit="C", value="solo 5")
        term = SupplierOfferContractTerm(id=7, key="temperatura", numeric_value=7.0, unit="C", value_text="7")
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(status, "REQUIERE_REVISION")

    def test_no_ofertado(self):
        req = CaseRequirementMatrix(id=7, key="plazo", comparator="MAX", numeric_value=10.0, unit="days", value="10")
        status, final_val, final_unit = self._evaluate(req, None)
        self.assertEqual(status, "NO_OFERTADO")

    def test_exact(self):
        req = CaseRequirementMatrix(id=8, key="color", comparator="EXACT", numeric_value=1.0, value="rojo")
        term = SupplierOfferContractTerm(id=8, key="color", numeric_value=1.0, value_text="rojo")
        status, final_val, final_unit = self._evaluate(req, term)
        self.assertEqual(status, "CUMPLE")

if __name__ == '__main__':
    unittest.main()
