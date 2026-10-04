"""R3 adapts one R2 assertion to its explicit unavailable response contract.

The original 14-test file remains frozen; all other tests are inherited intact.
"""
import sqlite3
import unittest
import typed_review_base as base


class IndependentR3(base.IndependentChecks):
    def test_foreign_reference_in_projection_is_refused(self):
        self.put()
        foreign = self.put("foreign", "foreign synthetic material", workspace="other")
        self.typed.sync("demo")
        with sqlite3.connect(self.index) as db:
            db.execute("UPDATE documents SET ref=?", (base.canonical(foreign),))
        result = self.typed.search("demo", "copper")
        self.assert_empty_status(result, "unavailable")
        self.assertEqual(result["reason"], "projection_scope_mismatch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
