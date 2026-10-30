import unittest
from appearance import sequence_findings, combine

def record(vial,lab):
    return dict(id=str(vial),seconds=vial*10,recipe=dict(vial=vial,recipe_id=(vial-1)//3),color=dict(lab=[lab,0,0],temporal_spread=0))

class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.recipes=[dict(vial=i,recipe_id=(i-1)//3,start_s=i*10) for i in range(1,7)]
    def test_waits_for_future_fills(self):
        result=sequence_findings([record(4,0),record(5,20)],self.recipes)
        self.assertEqual(result['4']['decision'],'insufficient evidence')
        self.assertNotIn('available_after_seconds',result['4'])
    def test_transition_requires_previous_output(self):
        records=[record(4,1),record(5,20),record(6,21)]
        self.assertEqual(sequence_findings(records,self.recipes)['4']['decision'],'appearance deviation - review')
        result=sequence_findings([record(3,0),*records],self.recipes)['4']
        self.assertEqual(result['decision'],'possible carryover pattern')
        self.assertEqual(result['available_after_seconds'],60)
    def test_disagreeing_later_pair(self):
        result=sequence_findings([record(4,0),record(5,20),record(6,40)],self.recipes)['4']
        self.assertEqual(result['decision'],'insufficient evidence')
    def test_agreement_is_not_pass(self):
        result=sequence_findings([record(4,20),record(5,21),record(6,20)],self.recipes)['4']
        self.assertEqual(result['decision'],'no clear appearance deviation')
    def test_model_cannot_override(self):
        for text in ('MATCH','Looks good','Polluted'):
            self.assertEqual(combine({'status':'appearance deviation - review'},text)['decision'],'appearance deviation - review')
        self.assertEqual(combine({'status':'insufficient evidence'},'MATCH')['decision'],'insufficient evidence')

if __name__=='__main__': unittest.main()
