import os
import unittest
from unittest.mock import patch
import creator_jev

class SavedExportTests(unittest.TestCase):
    def test_export_reuses_valid_judgment_and_refuses_paid_refresh_after_model_changes(self):
        creator_jev._cache.clear()
        evidence={"recent_titles":["唇膏试用与唇护理"],"category":"美妆","content_evidence_reviewed":True}
        rules={"category":"美妆","product_name":"唇护理"}
        response={"answers":{"content_fit":{"choice":"supported","confidence":0.9}},"model":"jev-latest"}
        config={"backend":"cloud","model":"jev-latest"}
        with patch.object(creator_jev,"enabled",return_value=True),patch.object(creator_jev,"settings",return_value=config),patch.object(creator_jev,"decide",return_value=response) as decide,patch.dict(os.environ,{"AIPR_JEV_SAVED_ONLY":"0"}):
            judgment=creator_jev.review(evidence,rules,"aipr-pro")
            self.assertEqual(judgment["route"],"supported")
            creator_jev._cache.clear();decide.reset_mock()
            with patch.dict(os.environ,{"AIPR_JEV_SAVED_ONLY":"1"}):
                result=creator_jev.review({**evidence,"jev_analysis":judgment},rules,"aipr-pro")
                self.assertEqual(result["route"],"supported");decide.assert_not_called()
                config["model"]="jev-preview"
                result=creator_jev.review({**evidence,"jev_analysis":judgment},rules,"aipr-pro")
                self.assertEqual(result["route"],"uncertain");self.assertTrue(result["needs_review"]);decide.assert_not_called()
