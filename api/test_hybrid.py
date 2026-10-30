import unittest
from hybrid import combine, prepare, BANK
import json

class HybridTests(unittest.TestCase):
    def test_disagreement_never_passes(self):
        self.assertEqual(combine({'status':'mismatch'},'MATCH\nLooks similar')['decision'],'review needed')
        self.assertEqual(combine({'status':'match'},'MISMATCH\nDifferent')['decision'],'review needed')
    def test_missing_evidence_never_passes(self):
        for text in ('UNCERTAIN','Looks good','',None):
            self.assertEqual(combine({'status':'match'},text)['decision'],'insufficient evidence')
        self.assertEqual(combine({'status':'match'},'MATCH','Tunnel failed')['decision'],'insufficient evidence')
    def test_both_agree(self):
        self.assertEqual(combine({'status':'match'},'MATCH\nSimilar')['decision'],'consistent')
    def test_held_out_target_excluded(self):
        bank=json.loads(BANK.read_text())
        r=bank['references'][0]
        result=prepare(dict(image=r['image'],recipe=dict(vial=1,recipe_id=5),source_video='vial_fill_video_5.mp4'))
        self.assertEqual(result['reference_vials'],[2,3])
        self.assertEqual(result['excluded_fold'],0)
        self.assertIn(result['status'],('match','mismatch'))


    def test_target_tank_context_keeps_two_regions(self):
        from hybrid import target_context, decode
        bank=json.loads(BANK.read_text())
        image=bank['references'][0]['image']
        context=decode(target_context({'image':image,'tank_image':image}))
        self.assertEqual(context.shape,(390,720,3))

if __name__=='__main__': unittest.main()

