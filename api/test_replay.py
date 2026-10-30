import unittest
import json
from pathlib import Path
from replay import CompletionTracker, sample_times

class Tracker(CompletionTracker):
    @staticmethod
    def crop(frame, box):
        return 'crop'

def box(x):
    return [x - .06, .1, x + .06, .9]

class CompletionTests(unittest.TestCase):
    def test_departure_and_no_duplicate(self):
        t = Tracker()
        for sec, x in [(0,.48),(1,.48),(1.3,.39),(1.6,.32)]:
            result = t.update(sec,[box(x)],None)
        self.assertEqual(result['latest']['seconds'],1)
        self.assertEqual(result['latest']['number'],1)
        self.assertEqual(t.update(2,[box(.25)],None)['latest']['number'],1)

    def test_missing_detection_is_not_completion(self):
        t = Tracker()
        t.update(0,[box(.48)],None)
        t.update(1,[box(.48)],None)
        self.assertIsNone(t.update(1.5,[],None)['latest'])
        self.assertIsNone(t.update(1.75,[box(.48)],None)['latest'])

    def test_fast_departure_after_brief_dropout(self):
        t = Tracker()
        t.update(0,[box(.48)],None)
        t.update(1,[box(.48)],None)
        t.update(1.25,[],None)
        self.assertEqual(t.update(1.5,[box(.30)],None)['latest']['number'],1)

    def test_long_dropout_discards_track(self):
        t = Tracker()
        t.update(0,[box(.48)],None)
        t.update(1,[box(.48)],None)
        t.update(2.25,[],None)
        self.assertIsNone(t.update(2.5,[box(.30)],None)['latest'])

    def test_departing_jar_is_not_replaced_by_incoming_jar(self):
        t = Tracker()
        t.update(0,[box(.48)],None)
        t.update(1,[box(.48)],None)
        self.assertEqual(t.update(1.25,[box(.15),box(.50)],None)['latest']['number'],1)

    def test_unrelated_vertical_box_does_not_complete(self):
        t = Tracker()
        t.update(0,[box(.48)],None)
        t.update(1,[box(.48)],None)
        self.assertIsNone(t.update(1.25,[[.2,.5,.4,.6]],None)['latest'])

    def test_four_recorded_departures(self):
        fixture = Path(__file__).parent / 'tests/fixtures/vial_departures.json'
        for case in json.loads(fixture.read_text())['cases']:
            with self.subTest(departure=case['departure']):
                t = Tracker()
                captured_at = []
                count = 0
                for row in case['observations']:
                    t.update(row['seconds'],row['boxes'],None)
                    if t.count != count:
                        captured_at.append(row['seconds'])
                        count = t.count
                self.assertEqual(captured_at,[case['departure']])

    def test_backlog_is_bounded_but_never_skips_frames(self):
        timestamps = []
        last = None
        # Simulate a browser jumping forward while inference is busy.
        while last is None or last < 10:
            batch = sample_times(last,10)
            self.assertLessEqual(len(batch),8)
            timestamps.extend(batch)
            last = batch[-1]
        self.assertEqual(timestamps,[i/4 for i in range(41)])
        self.assertEqual(sample_times(last,10),[])
        self.assertEqual(sample_times(last,10.1),[])

    def test_short_visit_and_rightward_motion(self):
        for positions in [[(0,.48),(.2,.39),(.4,.32)],[(0,.48),(1,.48),(1.2,.57),(1.4,.63)]]:
            t = Tracker()
            for sec,x in positions:
                result=t.update(sec,[box(x)],None)
            self.assertIsNone(result['latest'])

    def test_seek_resets_track(self):
        t = Tracker()
        t.update(5,[box(.48)],None)
        t.update(6,[box(.48)],None)
        self.assertIsNone(t.update(0,[box(.39)],None)['latest'])
        self.assertIsNone(t.update(10,[box(.32)],None)['latest'])

if __name__ == '__main__':
    unittest.main()
