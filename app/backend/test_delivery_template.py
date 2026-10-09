import unittest
from delivery_template import apply_template

class TemplateTests(unittest.TestCase):
    def test_lip_export_preserves_evidence_and_contacts_without_underwear_columns(self):
        original={"rows":[{"达人昵称":"样本","微信":"wx-example","内容证据":"唇护理作品","身高(cm)":165,"内衣单品":"旧字段"}],"robot_queue":[{"creator":{"id":"same-id"}}]}
        source_row=dict(original["rows"][0])
        result=apply_template(original,{"category":"美妆个护"})
        self.assertNotIn("身高(cm)",result["rows"][0]);self.assertNotIn("内衣单品",result["rows"][0])
        self.assertEqual(result["rows"][0]["内容证据"],"唇护理作品");self.assertEqual(result["robot_queue"][0]["creator"]["id"],"same-id")
        self.assertIn("身高(cm)",source_row);self.assertEqual(result["export_template"]["version"],3)
    def test_apparel_rules_keep_required_fields(self):
        result=apply_template({"rows":[{"身高(cm)":165,"内衣单品":"产品"}]},{"category":"服饰内衣"})
        self.assertEqual(result["rows"][0]["身高(cm)"],165)
