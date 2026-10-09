import unittest
from audit_strict_contact_highwater import merged_audit_rules


class DeliveryExclusionScopeTests(unittest.TestCase):
    def test_replenishment_does_not_exclude_current_delivery(self):
        rules = merged_audit_rules({"excludeIdentities": ["historical", "current"],
                                  "deliveryExcludeIdentities": ["historical"]}, {})
        self.assertEqual(rules["excludeIdentities"], ["historical"])

    def test_historical_exclusions_and_contacts_remain(self):
        rules = merged_audit_rules({"deliveryExcludeIdentities": [], "excludeContacts": ["current-contact"]},
                                  {"excludeIdentities": ["old"], "excludeContacts": ["old-contact"]})
        self.assertEqual(rules["excludeIdentities"], ["old"])
        self.assertEqual(set(rules["excludeContacts"]), {"current-contact", "old-contact"})

    def test_legacy_rules_preserve_exclusions(self):
        self.assertEqual(merged_audit_rules({"excludeIdentities": ["old"]}, {})["excludeIdentities"], ["old"])
