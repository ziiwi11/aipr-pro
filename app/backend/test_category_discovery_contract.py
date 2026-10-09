import unittest
from unittest.mock import patch
from collect_and_contact_pipeline import require_keyword_replenishment

class CategoryDiscoveryContractTest(unittest.TestCase):
    def test_category_exhaustion_never_silently_switches_to_keywords(self):
        for mode in ("structured_browse", "browse", "filter_browse"):
            strategy={"sourceDiscoveryMode":mode,"keywords":[]}
            with patch("collect_and_contact_pipeline.emit") as notify:
                with self.assertRaises(SystemExit) as error:
                    require_keyword_replenishment(strategy)
                self.assertEqual(error.exception.code,7)
                self.assertEqual(strategy["sourceDiscoveryMode"],mode)
                self.assertEqual(strategy["keywords"],[])
                self.assertIn("不切换关键词",notify.call_args.args[0]["message"])
    def test_keyword_search_can_still_replenish(self):
        require_keyword_replenishment({"sourceDiscoveryMode":"keyword_search"})
