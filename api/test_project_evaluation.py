import csv
from pathlib import Path
import unittest

P=Path(__file__).resolve().parent/'final_evaluation/predictions.csv'
@unittest.skipUnless(P.exists(),'Run evaluate_project.py first')
class ProjectEvaluationTests(unittest.TestCase):
    def test_holdout_and_reference_exclusion(self):
        rows=list(csv.DictReader(P.read_text().splitlines()))
        loro=[r for r in rows if r['mode']=='leave_one_recipe_out']
        self.assertEqual(len(loro),30)
        self.assertTrue(all(r['held_out_recipe']!=r['reference_recipe'] for r in loro))
        retro=[r for r in rows if r['mode']=='retrospective_third_vial']
        self.assertEqual(len(retro),20)
        self.assertTrue(all(r['vial']!=r['reference_vial'] for r in retro))
        for mode in ('leave_one_recipe_out','retrospective_third_vial'):
            first=next(r for r in rows if r['mode']==mode and r['vial']=='1')
            self.assertEqual(first['truth'],'')

if __name__=='__main__': unittest.main()
