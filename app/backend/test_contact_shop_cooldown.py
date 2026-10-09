import json,tempfile,time,unittest
from pathlib import Path
from contact_shop_cooldown import shop_cooldown_until
class Tests(unittest.TestCase):
 def test_scoping(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); t=time.time()+1200
   (p/'.contact_rate_limit_until').write_text(str(t))
   self.assertEqual(shop_cooldown_until(p,'B'),t)
   (p/'ui_contact_icon_retry_A_1.json').write_text(json.dumps({'candidates':[{'ui_contact_probe_status':'rate_limited','ui_contact_message':'请求过于频繁，请稍后再试','ui_contact_rate_limit_until':t-600}]}))
   self.assertEqual(shop_cooldown_until(p,'A'),t)
   self.assertEqual(shop_cooldown_until(p,'B'),0)
   (p/'.contact_rate_limit_until_B').write_text(str(t+30))
   self.assertEqual(shop_cooldown_until(p,'B'),t+30)
