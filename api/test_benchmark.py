"""Audit the completed benchmark's pairing, folds and metric counts."""
import csv
import json
import unittest
from pathlib import Path

OUT=Path(__file__).resolve().parent/'benchmark_results'

@unittest.skipUnless((OUT/'predictions.csv').exists(), 'Run benchmark first')
class BenchmarkAudit(unittest.TestCase):
    def test_complete_balanced_run(self):
        rows=list(csv.DictReader((OUT/'predictions.csv').read_text().splitlines()))
        for method in ('color_distance','cosmos'):
            subset=[r for r in rows if r['method']==method]
            self.assertEqual(len(subset),90)
            self.assertEqual(len({r['vial'] for r in subset}),30)
            for r in subset:
                self.assertEqual(int(r['fold']), (int(r['vial'])-1)%3)
                if r['task']=='consistency':
                    recipe=5+(int(r['vial'])-1)//3
                    self.assertEqual(r['truth']=='match',int(r['supplied_recipe'])==recipe)
            self.assertEqual(sum(r['truth']=='mismatch' for r in subset),30)
            self.assertEqual(sum(r['truth']=='match' for r in subset),30)
            self.assertFalse(any(r['prediction']=='error' for r in subset))

    def test_metrics_match_raw_predictions(self):
        rows=list(csv.DictReader((OUT/'predictions.csv').read_text().splitlines()))
        summary=json.loads((OUT/'metrics.json').read_text())
        for method in ('color_distance','cosmos'):
            selected=[r for r in rows if r['method']==method and r['task']=='recognition']
            accuracy=sum(r['truth']==r['prediction'] for r in selected)/30
            self.assertAlmostEqual(accuracy,summary[method]['recognition_accuracy'],places=4)

if __name__=='__main__': unittest.main()

