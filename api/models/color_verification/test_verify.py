"""Offline contract and failure tests; no inference server or credentials needed."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import requests

from models.color_verification.verify import VerificationError, parse_result, verify_color


ASSESSMENT = {
    "verdict": "uncertain",
    "observed_color": "Pale green",
    "expected_color": "Unknown without quantities",
    "explanation": "The recipe does not specify mixing ratios.",
    "potential_causes": [],
    "limitations": ["Unknown ratios"],
}


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / "vial.png"
        Image.new("RGB", (16, 16), "green").save(self.image)
        self.env_file = Path(self.temp.name) / ".env"
        self.env_file.write_text('BREV_API_KEY="test-key"\nCOSMOS_BASE_URL="http://localhost:8000/v1"\n')
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.post = patch("models.color_verification.verify.requests.post").start()
        self.addCleanup(patch.stopall)
        self.post.return_value = Mock(status_code=200)
        self.post.return_value.json.return_value = {"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(ASSESSMENT)}
        }]}

    def verify(self, **kwargs):
        return verify_color(self.image, self.image, "Jug A + Jug B", env_file=self.env_file, **kwargs)

    def test_images_history_and_authentication(self):
        history = [{"recipe": "Jug C", "good": False, "notes": "Red tint"}]
        result = self.verify(previous_recipes=history)
        self.assertEqual(result.verdict, "uncertain")
        args, kwargs = self.post.call_args
        self.assertEqual(args[0], "http://localhost:8000/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        content = kwargs["json"]["messages"][1]["content"]
        images = [part for part in content if part["type"] == "image_url"]
        self.assertEqual(len(images), 2)
        self.assertTrue(images[0]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertIn('"good":false', content[-1]["text"])

    def test_inference_key_overrides_brev_key(self):
        os.environ["COSMOS_API_KEY"] = "inference-key"
        self.verify()
        self.assertEqual(self.post.call_args.kwargs["headers"]["Authorization"], "Bearer inference-key")

    def test_missing_endpoint_makes_no_request(self):
        os.environ["COSMOS_BASE_URL"] = ""
        with self.assertRaises(VerificationError):
            self.verify()
        self.post.assert_not_called()

    def test_invalid_history_makes_no_request(self):
        with self.assertRaises(ValueError):
            self.verify(previous_recipes=[{"recipe": "Jug A", "good": "false"}])
        self.post.assert_not_called()

    def test_invalid_image_makes_no_request(self):
        self.image.write_bytes(b"not an image")
        with self.assertRaises(ValueError):
            self.verify()
        self.post.assert_not_called()

    def test_http_error_does_not_leak_response_body(self):
        self.post.return_value.status_code = 401
        self.post.return_value.text = "secret-token"
        with self.assertRaisesRegex(VerificationError, "HTTP 401") as caught:
            self.verify()
        self.assertNotIn("secret-token", str(caught.exception))

    def test_timeout_is_not_a_verdict(self):
        self.post.side_effect = requests.Timeout()
        with self.assertRaisesRegex(VerificationError, "timed out"):
            self.verify()

    def test_truncated_result_is_rejected(self):
        self.post.return_value.json.return_value["choices"][0]["finish_reason"] = "length"
        with self.assertRaisesRegex(VerificationError, "finish normally"):
            self.verify()

    def test_unexpected_response_is_rejected(self):
        for response in [{}, {"choices": []}, {"choices": [None]},
                         {"choices": [{"finish_reason": "stop", "message": None}]}]:
            with self.subTest(response=response):
                self.post.return_value.json.return_value = response
                with self.assertRaises(VerificationError):
                    self.verify()

    def test_wrapped_answer(self):
        content = '<think>internal text</think><answer>```json\n' + json.dumps(ASSESSMENT) + '\n```</answer>'
        self.assertEqual(parse_result(content).verdict, "uncertain")

    def test_invalid_output_is_rejected(self):
        for content in ['not json', '{}', json.dumps({**ASSESSMENT, "verdict": "good"}),
                        json.dumps({**ASSESSMENT, "verdict": "implausible"})]:
            with self.subTest(content=content), self.assertRaises(VerificationError):
                parse_result(content)

    def test_implausible_with_possible_residue(self):
        result = parse_result(json.dumps({**ASSESSMENT, "verdict": "implausible",
            "potential_causes": [{"cause": "Possible residue", "evidence": "Previous green batch",
                                  "suggested_check": "Flush tubing and repeat"}]}))
        self.assertEqual(len(result.potential_causes), 1)


if __name__ == "__main__":
    unittest.main()
