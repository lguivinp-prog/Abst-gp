import unittest
from app.services.v6.evaluation.vfm_service import ValueForMoneyService
from app.models.v6.supplier_offer import SupplierOffer
from app.models.v6.supplier_offer_contract_term import SupplierOfferContractTerm

class TestVFM(unittest.TestCase):
    def test_vfm_deltas(self):
        from unittest.mock import MagicMock
        from app.models.v6.supplier_offer_contract_term import SupplierOfferContractTerm

        db = MagicMock()
        service = ValueForMoneyService(db)

        offer_a = SupplierOffer(id=1, total_amount=9500.0)
        offer_b = SupplierOffer(id=2, total_amount=9900.0)

        terms_a = [
            SupplierOfferContractTerm(supplier_offer_id=1, key="plazo", numeric_value=10.0, unit="days"),
            SupplierOfferContractTerm(supplier_offer_id=1, key="garantia", numeric_value=12.0, unit="months")
        ]

        terms_b = [
            SupplierOfferContractTerm(supplier_offer_id=2, key="plazo", numeric_value=5.0, unit="days"),
            SupplierOfferContractTerm(supplier_offer_id=2, key="garantia", numeric_value=24.0, unit="months")
        ]

        # db.query().filter_by().all() is called for A, then B
        db.query.return_value.filter_by.return_value.all.side_effect = [terms_a, terms_b]

        result = service.compare(offer_a, offer_b)

        self.assertAlmostEqual(result["price"]["absolute_delta"], 400.0)
        self.assertAlmostEqual(result["price"]["percent_delta"], 4.21, places=2)

        self.assertAlmostEqual(result["delivery_term"]["absolute_delta"], -5.0)
        self.assertAlmostEqual(result["delivery_term"]["percent_delta"], -50.0)

        self.assertAlmostEqual(result["warranty"]["absolute_delta"], 12.0)
        self.assertAlmostEqual(result["warranty"]["percent_delta"], 100.0)

        self.assertEqual(result["automatic_winner"], "NONE")

if __name__ == '__main__':
    unittest.main()
