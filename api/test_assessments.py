import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from assessments import AssessmentService, match_recipe, assess, load_tank_context, capture_tank_frame


class AssessmentTests(unittest.TestCase):
    def test_tank_frame_uses_crop_timestamp_and_offset(self):
        with patch('assessments.load_dotenv'), patch.dict('os.environ', {'TANK_VIDEO_OFFSET_SECONDS': '2'}):
            frame = capture_tank_frame(28)
        self.assertEqual(frame['tank_requested_seconds'], 30)
        self.assertAlmostEqual(frame['tank_frame_seconds'], 30, delta=0.1)
        self.assertTrue(frame['tank_image'].startswith('data:image/jpeg;base64,'))
        self.assertEqual(frame['tank_source'], 'tank_level_video_5.mp4')

    def test_missing_tank_frame_fails_without_static_fallback(self):
        with patch('assessments.load_dotenv'), patch.dict('os.environ', {'TANK_VIDEO_OFFSET_SECONDS': '0'}):
            with self.assertRaisesRegex(ValueError, 'outside the recording'):
                capture_tank_frame(1000000)

    def test_confirmed_colors_require_provenance(self):
        import json
        context = load_tank_context()
        context['tanks']['100'].update(confirmed=True, color='blue', confirmed_by=None)
        with patch('assessments.Path.read_text', return_value=json.dumps(context)):
            with self.assertRaisesRegex(ValueError, 'confirmed_by'):
                load_tank_context()

    def test_tank_context_sent_with_both_images(self):
        with patch('assessments.load_dotenv'), patch.dict('os.environ', {
            'COSMOS_BASE_URL': 'http://localhost:8001/v1', 'COSMOS_API_KEY': 'test',
        }), patch('assessments.requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'choices': [{
                'finish_reason': 'stop', 'message': {'content': 'Uncertain - test'},
            }]}
            context = load_tank_context()
            assess(dict(image='vial', tank_image='tank', recipe={}, seconds=28,
                        previous_recipes=[], tank_context=context))
            content = post.call_args.kwargs['json']['messages'][0]['content']
            self.assertEqual([c['image_url']['url'] for c in content if c['type'] == 'image_url'], ['tank', 'vial'])
            import json
            self.assertEqual(json.loads(content[-1]['text'])['tank_context'], context)

    def test_timestamp_matching_and_departure_grace(self):
        recipes = [dict(vial=1, start_s=0, end_s=26.894),
                   dict(vial=2, start_s=46.204, end_s=73.645)]
        self.assertEqual(match_recipe(28, recipes)['vial'], 1)
        self.assertEqual(match_recipe(47, recipes)['vial'], 2)
        for seconds in (32, 45, 90):
            with self.assertRaises(ValueError):
                match_recipe(seconds, recipes)

    def test_overlapping_recipes_are_rejected(self):
        recipes = [dict(start_s=0, end_s=10), dict(start_s=0, end_s=20)]
        # Identical start times indicate invalid/ambiguous recipe metadata.
        with self.assertRaises(ValueError):
            match_recipe(5, recipes)

    def test_queue_retains_every_crop_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def evaluate(record):
                calls.append(record['number'])
                return 'Uncertain — example.', 'test-model'
            service = AssessmentService(Path(directory), evaluate)
            for number, seconds in ((1, 28), (2, 74), (1, 28)):
                service.submit('test', dict(number=number, seconds=seconds, image='test-image'))
            service.queue.join()
            self.assertEqual(calls, [1, 2])
            self.assertEqual([r['recipe']['vial'] for r in service.list('test')], [1, 2])
            self.assertTrue(all(r['status'] == 'complete' for r in service.list('test')))
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 2)

    def test_error_is_not_a_verdict_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            def fail(record):
                raise ValueError('Tunnel unavailable')
            service = AssessmentService(Path(directory), fail)
            job = service.submit('test', dict(number=1, seconds=28, image='test-image'))
            service.queue.join()
            record = service.list('test')[0]
            self.assertEqual(record['status'], 'error')
            self.assertIsNone(record['text'])
            service.evaluator = lambda record: ('Looks good — test.', 'test')
            service.retry(job)
            service.queue.join()
            self.assertEqual(service.list('test')[0]['status'], 'complete')

    def test_truncated_model_answer_is_rejected(self):
        with patch('assessments.load_dotenv'), patch.dict('os.environ', {
            'COSMOS_BASE_URL': 'http://localhost:8001/v1', 'COSMOS_API_KEY': 'test',
        }), patch('assessments.requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'choices': [{
                'finish_reason': 'length', 'message': {'content': 'Looks good'},
            }]}
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                assess(dict(image='image', tank_image='image', recipe={}, seconds=28, previous_recipes=[]))


if __name__ == '__main__':
    unittest.main()
